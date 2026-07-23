from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models import Asset
from app.models.enums import AssetType, FindingSeverity
from app.security_rules.base import Evaluator, RuleContext, SecurityRule
from app.security_rules.results import RuleResult, error, failed, passed


def _predicate(required: tuple[str, ...], predicate: Any) -> Evaluator:
    def evaluate(asset: Asset | None, _context: RuleContext) -> RuleResult:
        assert asset is not None
        if any(field not in asset.metadata_json for field in required):
            return error()
        evidence = {field: asset.metadata_json[field] for field in required}
        return failed(**evidence) if predicate(evidence) else passed(**evidence)

    return evaluate


def _access_key_age(asset: Asset | None, context: RuleContext) -> RuleResult:
    assert asset is not None
    values = asset.metadata_json.get("active_key_created_at")
    if not isinstance(values, list):
        return error()
    ages: list[int] = []
    for value in values:
        if not isinstance(value, str):
            return error("malformed_access_key_metadata")
        try:
            created = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return error("malformed_access_key_metadata")
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        ages.append((context.evaluated_at - created).days)
    oldest = max(ages, default=0)
    return (
        failed(oldest_active_key_age_days=oldest)
        if oldest > 90
        else passed(oldest_active_key_age_days=oldest)
    )


def _inline_allow_all(asset: Asset | None, _context: RuleContext) -> RuleResult:
    assert asset is not None
    documents = asset.metadata_json.get("inline_policy_documents")
    if not isinstance(documents, list):
        return error()
    for document in documents:
        if not isinstance(document, dict):
            return error("malformed_inline_policy")
        statements = document.get("Statement")
        if isinstance(statements, dict):
            statements = [statements]
        if not isinstance(statements, list):
            return error("malformed_inline_policy")
        for statement in statements:
            if not isinstance(statement, dict):
                return error("malformed_inline_policy")
            effect = statement.get("Effect")
            actions = statement.get("Action")
            resources = statement.get("Resource")
            if not isinstance(effect, str):
                return error("malformed_inline_policy")
            if isinstance(actions, str):
                actions = [actions]
            if isinstance(resources, str):
                resources = [resources]
            if not isinstance(actions, list) or not all(isinstance(v, str) for v in actions):
                return error("malformed_inline_policy")
            if not isinstance(resources, list) or not all(isinstance(v, str) for v in resources):
                return error("malformed_inline_policy")
            if effect == "Allow" and "*" in actions and "*" in resources:
                return failed(statement_index=statements.index(statement))
    return passed()


RULES = (
    SecurityRule(
        "IAM_USER_CONSOLE_ACCESS_WITHOUT_MFA",
        1,
        "Console user has no MFA",
        "An IAM user has console access but no active MFA device.",
        "iam",
        AssetType.IAM_USER,
        "identity",
        FindingSeverity.CRITICAL,
        "Enroll an MFA device or remove console access.",
        evaluator=_predicate(
            ("console_access", "mfa_enabled"),
            lambda e: e["console_access"] and not e["mfa_enabled"],
        ),
    ),
    SecurityRule(
        "IAM_USER_ACCESS_KEY_TOO_OLD",
        1,
        "IAM access key is too old",
        "At least one active access key exceeds the configured 90-day threshold.",
        "iam",
        AssetType.IAM_USER,
        "credential_hygiene",
        FindingSeverity.HIGH,
        "Rotate or remove the old access key.",
        evaluator=_access_key_age,
    ),
    SecurityRule(
        "IAM_ADMINISTRATOR_ACCESS_ATTACHED",
        1,
        "AdministratorAccess attached",
        "The principal has the AWS AdministratorAccess managed policy attached.",
        "iam",
        AssetType.IAM_USER,
        "least_privilege",
        FindingSeverity.CRITICAL,
        "Replace AdministratorAccess with a least-privilege policy.",
        additional_asset_types=(AssetType.IAM_ROLE, AssetType.IAM_GROUP),
        evaluator=_predicate(
            ("attached_policy_arns",),
            lambda e: any(
                str(v).endswith("/AdministratorAccess") for v in e["attached_policy_arns"]
            ),
        ),
    ),
    SecurityRule(
        "IAM_INLINE_POLICY_ALLOW_ALL",
        1,
        "Inline policy allows all actions",
        "The bounded inline-policy summary confirms an Allow * action.",
        "iam",
        AssetType.IAM_USER,
        "least_privilege",
        FindingSeverity.CRITICAL,
        "Replace wildcard administrative permissions with scoped actions and resources.",
        additional_asset_types=(AssetType.IAM_ROLE, AssetType.IAM_GROUP),
        evaluator=_inline_allow_all,
    ),
)
