from __future__ import annotations

from typing import Any

from app.models import Asset
from app.models.enums import AssetType, FindingSeverity
from app.security_rules.base import Evaluator, RuleContext, SecurityRule
from app.security_rules.results import RuleResult, error, failed, passed


def _rule(field: str, predicate: Any) -> Evaluator:
    def evaluate(asset: Asset | None, _context: RuleContext) -> RuleResult:
        assert asset is not None
        if field not in asset.metadata_json:
            return error()
        value = asset.metadata_json[field]
        return failed(**{field: value}) if predicate(value) else passed(**{field: value})

    return evaluate


RULES = (
    SecurityRule(
        "RDS_INSTANCE_PUBLICLY_ACCESSIBLE",
        1,
        "RDS is publicly accessible",
        "The RDS instance is marked publicly accessible.",
        "rds",
        AssetType.RDS_INSTANCE,
        "exposure",
        FindingSeverity.CRITICAL,
        "Disable public accessibility.",
        evaluator=_rule("publicly_accessible", bool),
    ),
    SecurityRule(
        "RDS_STORAGE_NOT_ENCRYPTED",
        1,
        "RDS storage is unencrypted",
        "Storage encryption is disabled.",
        "rds",
        AssetType.RDS_INSTANCE,
        "data_protection",
        FindingSeverity.HIGH,
        "Migrate to an encrypted database.",
        evaluator=_rule("storage_encrypted", lambda value: value is False),
    ),
    SecurityRule(
        "RDS_BACKUP_RETENTION_INSUFFICIENT",
        1,
        "Backup retention is insufficient",
        "Automated backup retention is less than seven days.",
        "rds",
        AssetType.RDS_INSTANCE,
        "resilience",
        FindingSeverity.MEDIUM,
        "Set backup retention to at least seven days.",
        evaluator=_rule("backup_retention_period", lambda value: int(value) < 7),
    ),
    SecurityRule(
        "RDS_AUTO_MINOR_VERSION_UPGRADE_DISABLED",
        1,
        "Automatic minor upgrades disabled",
        "Automatic minor version upgrades are disabled.",
        "rds",
        AssetType.RDS_INSTANCE,
        "patching",
        FindingSeverity.MEDIUM,
        "Enable automatic minor version upgrades.",
        evaluator=_rule("auto_minor_version_upgrade", lambda value: value is False),
    ),
    SecurityRule(
        "RDS_DELETION_PROTECTION_DISABLED",
        1,
        "Deletion protection disabled",
        "Database deletion protection is disabled.",
        "rds",
        AssetType.RDS_INSTANCE,
        "resilience",
        FindingSeverity.MEDIUM,
        "Enable deletion protection.",
        evaluator=_rule("deletion_protection", lambda value: value is False),
    ),
)
