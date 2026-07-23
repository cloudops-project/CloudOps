from __future__ import annotations

from collections.abc import Iterable

from app.models.enums import AssetType, FindingSeverity
from app.security_rules.base import SecurityRule
from app.security_rules.cloudtrail import RULES as CLOUDTRAIL_RULES
from app.security_rules.cloudwatch import RULES as CLOUDWATCH_RULES
from app.security_rules.ec2 import RULES as EC2_RULES
from app.security_rules.iam import RULES as IAM_RULES
from app.security_rules.rds import RULES as RDS_RULES
from app.security_rules.s3 import RULES as S3_RULES


class RuleRegistry:
    def __init__(self, rules: Iterable[SecurityRule]) -> None:
        self._rules: dict[str, SecurityRule] = {}
        for rule in rules:
            if rule.key in self._rules:
                raise ValueError(f"Duplicate rule key: {rule.key}")
            self._rules[rule.key] = rule

    def all(self) -> tuple[SecurityRule, ...]:
        return tuple(self._rules[key] for key in sorted(self._rules))

    def get(self, key: str) -> SecurityRule | None:
        return self._rules.get(key)

    def filter(
        self,
        *,
        service: str | None = None,
        asset_type: AssetType | None = None,
        severity: FindingSeverity | None = None,
        category: str | None = None,
        enabled: bool | None = None,
    ) -> tuple[SecurityRule, ...]:
        return tuple(
            rule
            for rule in self.all()
            if (service is None or rule.service == service)
            and (asset_type is None or asset_type in rule.asset_types)
            and (severity is None or rule.severity == severity)
            and (category is None or rule.category == category)
            and (enabled is None or rule.enabled_by_default is enabled)
        )

    @property
    def services(self) -> tuple[str, ...]:
        return tuple(sorted({rule.service for rule in self._rules.values()}))

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(sorted({rule.category for rule in self._rules.values()}))


default_registry = RuleRegistry(
    (*EC2_RULES, *S3_RULES, *IAM_RULES, *RDS_RULES, *CLOUDWATCH_RULES, *CLOUDTRAIL_RULES)
)
