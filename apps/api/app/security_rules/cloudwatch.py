from __future__ import annotations

from app.models import Asset
from app.models.enums import AssetType, FindingSeverity
from app.security_rules.base import RuleContext, SecurityRule
from app.security_rules.results import RuleResult, error, failed, passed


def _missing_retention(asset: Asset | None, _context: RuleContext) -> RuleResult:
    assert asset is not None
    if "retention_days" not in asset.metadata_json:
        return failed(retention_days=None)
    value = asset.metadata_json["retention_days"]
    return failed(retention_days=value) if value is None else passed(retention_days=value)


def _not_encrypted(asset: Asset | None, _context: RuleContext) -> RuleResult:
    assert asset is not None
    if "kms_encrypted" not in asset.metadata_json:
        return error()
    return (
        failed(kms_encrypted=False)
        if asset.metadata_json["kms_encrypted"] is False
        else passed(kms_encrypted=True)
    )


def _actions_disabled(asset: Asset | None, _context: RuleContext) -> RuleResult:
    assert asset is not None
    if "actions_enabled" not in asset.metadata_json:
        return error()
    value = asset.metadata_json["actions_enabled"]
    return failed(actions_enabled=value) if value is False else passed(actions_enabled=value)


RULES = (
    SecurityRule(
        "CLOUDWATCH_LOG_GROUP_RETENTION_NOT_CONFIGURED",
        1,
        "CloudWatch log retention is not configured",
        "The log group retains events indefinitely.",
        "cloudwatch_logs",
        AssetType.CLOUDWATCH_LOG_GROUP,
        "logging",
        FindingSeverity.MEDIUM,
        "Configure an approved retention period.",
        evaluator=_missing_retention,
    ),
    SecurityRule(
        "CLOUDWATCH_LOG_GROUP_NOT_KMS_ENCRYPTED",
        1,
        "CloudWatch log group is not KMS encrypted",
        "The log group has no KMS key association.",
        "cloudwatch_logs",
        AssetType.CLOUDWATCH_LOG_GROUP,
        "data_protection",
        FindingSeverity.MEDIUM,
        "Associate an approved KMS key.",
        evaluator=_not_encrypted,
    ),
    SecurityRule(
        "CLOUDWATCH_ALARM_ACTIONS_DISABLED",
        1,
        "CloudWatch alarm actions disabled",
        "The alarm cannot invoke configured actions.",
        "cloudwatch",
        AssetType.CLOUDWATCH_ALARM,
        "monitoring",
        FindingSeverity.MEDIUM,
        "Enable alarm actions.",
        evaluator=_actions_disabled,
    ),
)
