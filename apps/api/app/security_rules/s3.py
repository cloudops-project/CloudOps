from __future__ import annotations

from typing import Any

from app.models import Asset
from app.models.enums import AssetType, FindingSeverity
from app.security_rules.base import Evaluator, RuleContext, SecurityRule
from app.security_rules.results import RuleResult, error, failed, passed


def _metadata_rule(field: str, unsafe: Any) -> Evaluator:
    def evaluate(asset: Asset | None, _context: RuleContext) -> RuleResult:
        assert asset is not None
        if field not in asset.metadata_json:
            return error()
        value = asset.metadata_json[field]
        return failed(**{field: value}) if value == unsafe else passed(**{field: value})

    return evaluate


def _public_confirmed(asset: Asset | None, _context: RuleContext) -> RuleResult:
    assert asset is not None
    signals = asset.metadata_json.get("public_access_signals")
    if not isinstance(signals, dict):
        return error()
    confirmed = any(value is True for value in signals.values())
    return failed(signals=signals) if confirmed else passed(signals=signals)


RULES = (
    SecurityRule(
        "S3_BUCKET_PUBLIC_ACCESS_CONFIRMED",
        1,
        "Public S3 access confirmed",
        "Stored S3 ACL or policy status confirms public access.",
        "s3",
        AssetType.S3_BUCKET,
        "exposure",
        FindingSeverity.CRITICAL,
        "Remove public grants and public policy statements.",
        evaluator=_public_confirmed,
    ),
    SecurityRule(
        "S3_BUCKET_PUBLIC_ACCESS_BLOCK_INCOMPLETE",
        1,
        "Public access block incomplete",
        "Not all S3 public-access-block controls are enabled.",
        "s3",
        AssetType.S3_BUCKET,
        "exposure",
        FindingSeverity.HIGH,
        "Enable all four S3 public access block controls.",
        evaluator=_metadata_rule("public_access_block_complete", False),
    ),
    SecurityRule(
        "S3_BUCKET_DEFAULT_ENCRYPTION_MISSING",
        1,
        "Default encryption missing",
        "Default server-side encryption is not configured.",
        "s3",
        AssetType.S3_BUCKET,
        "data_protection",
        FindingSeverity.HIGH,
        "Configure default SSE-S3 or SSE-KMS encryption.",
        evaluator=_metadata_rule("default_encryption_enabled", False),
    ),
    SecurityRule(
        "S3_BUCKET_VERSIONING_DISABLED",
        1,
        "Versioning disabled",
        "S3 object versioning is disabled.",
        "s3",
        AssetType.S3_BUCKET,
        "resilience",
        FindingSeverity.MEDIUM,
        "Enable S3 versioning.",
        evaluator=_metadata_rule("versioning_enabled", False),
    ),
    SecurityRule(
        "S3_BUCKET_HTTPS_ONLY_POLICY_MISSING",
        1,
        "HTTPS-only policy missing",
        "The bounded policy signal does not confirm HTTPS-only access.",
        "s3",
        AssetType.S3_BUCKET,
        "transport",
        FindingSeverity.HIGH,
        "Add a bucket policy denying requests when aws:SecureTransport is false.",
        evaluator=_metadata_rule("https_only_policy", False),
    ),
    SecurityRule(
        "S3_BUCKET_LOGGING_DISABLED",
        1,
        "Access logging disabled",
        "S3 server access logging is disabled.",
        "s3",
        AssetType.S3_BUCKET,
        "logging",
        FindingSeverity.MEDIUM,
        "Enable access logging to an approved log bucket.",
        evaluator=_metadata_rule("logging_enabled", False),
    ),
)
