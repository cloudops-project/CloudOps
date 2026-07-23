from __future__ import annotations

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
        evaluator=_predicate(
            ("oldest_active_key_age_days",), lambda e: e["oldest_active_key_age_days"] > 90
        ),
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
        evaluator=_predicate(
            ("inline_policy_allow_all",), lambda e: e["inline_policy_allow_all"] is True
        ),
    ),
)
