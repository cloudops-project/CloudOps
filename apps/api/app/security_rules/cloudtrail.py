from __future__ import annotations

from typing import Any

from app.models import Asset
from app.models.enums import AssetType, FindingSeverity
from app.security_rules.base import Evaluator, RuleContext, SecurityRule
from app.security_rules.results import RuleResult, error, failed, passed


def _field(field: str, unsafe: Any) -> Evaluator:
    def evaluate(asset: Asset | None, _context: RuleContext) -> RuleResult:
        assert asset is not None
        if field not in asset.metadata_json:
            return error()
        value = asset.metadata_json[field]
        return failed(**{field: value}) if value == unsafe else passed(**{field: value})

    return evaluate


def _no_active(_asset: Asset | None, context: RuleContext) -> RuleResult:
    trails = context.assets_of_type(AssetType.CLOUDTRAIL_TRAIL)
    if not trails:
        return failed(active_trails=0)
    states = [trail.metadata_json.get("is_logging") for trail in trails]
    if any(state is True for state in states):
        return passed(active_trails=sum(state is True for state in states))
    if any(state is None for state in states):
        return error()
    return failed(active_trails=0)


RULES = (
    SecurityRule(
        "CLOUDTRAIL_NO_ACTIVE_TRAIL",
        1,
        "No active CloudTrail trail",
        "No persisted CloudTrail configuration confirms active logging.",
        "cloudtrail",
        None,
        "logging",
        FindingSeverity.CRITICAL,
        "Create and enable a multi-region trail.",
        evaluator=_no_active,
    ),
    SecurityRule(
        "CLOUDTRAIL_LOGGING_DISABLED",
        1,
        "CloudTrail logging disabled",
        "The trail is not currently logging.",
        "cloudtrail",
        AssetType.CLOUDTRAIL_TRAIL,
        "logging",
        FindingSeverity.CRITICAL,
        "Start logging for the trail.",
        evaluator=_field("is_logging", False),
    ),
    SecurityRule(
        "CLOUDTRAIL_NOT_MULTI_REGION",
        1,
        "CloudTrail is not multi-region",
        "The trail does not cover all AWS regions.",
        "cloudtrail",
        AssetType.CLOUDTRAIL_TRAIL,
        "coverage",
        FindingSeverity.HIGH,
        "Convert the trail to multi-region.",
        evaluator=_field("is_multi_region", False),
    ),
    SecurityRule(
        "CLOUDTRAIL_GLOBAL_EVENTS_DISABLED",
        1,
        "Global events disabled",
        "Global service events are excluded.",
        "cloudtrail",
        AssetType.CLOUDTRAIL_TRAIL,
        "coverage",
        FindingSeverity.HIGH,
        "Enable global service event collection.",
        evaluator=_field("include_global_service_events", False),
    ),
    SecurityRule(
        "CLOUDTRAIL_LOG_VALIDATION_DISABLED",
        1,
        "Log validation disabled",
        "CloudTrail log-file integrity validation is disabled.",
        "cloudtrail",
        AssetType.CLOUDTRAIL_TRAIL,
        "integrity",
        FindingSeverity.MEDIUM,
        "Enable log-file validation.",
        evaluator=_field("log_file_validation_enabled", False),
    ),
    SecurityRule(
        "CLOUDTRAIL_NOT_KMS_ENCRYPTED",
        1,
        "CloudTrail is not KMS encrypted",
        "No KMS key is configured for the trail.",
        "cloudtrail",
        AssetType.CLOUDTRAIL_TRAIL,
        "data_protection",
        FindingSeverity.MEDIUM,
        "Configure an approved KMS key.",
        evaluator=_field("kms_encrypted", False),
    ),
    SecurityRule(
        "CLOUDTRAIL_CLOUDWATCH_INTEGRATION_MISSING",
        1,
        "CloudWatch Logs integration missing",
        "The trail is not integrated with CloudWatch Logs.",
        "cloudtrail",
        AssetType.CLOUDTRAIL_TRAIL,
        "monitoring",
        FindingSeverity.MEDIUM,
        "Configure CloudWatch Logs delivery.",
        evaluator=_field("cloudwatch_integration", False),
    ),
    SecurityRule(
        "CLOUDTRAIL_DELIVERY_FAILURE",
        1,
        "CloudTrail delivery is failing",
        "The latest delivery status reports an error.",
        "cloudtrail",
        AssetType.CLOUDTRAIL_TRAIL,
        "logging",
        FindingSeverity.CRITICAL,
        "Correct the trail destination and delivery permissions.",
        evaluator=_field("delivery_failed", True),
    ),
)
