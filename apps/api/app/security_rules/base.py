from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.models import Asset
from app.models.enums import AssetType, FindingSeverity
from app.security_rules.results import RuleResult


@dataclass(frozen=True)
class RuleContext:
    account_assets: tuple[Asset, ...]
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def assets_of_type(self, asset_type: AssetType) -> tuple[Asset, ...]:
        return tuple(asset for asset in self.account_assets if asset.asset_type == asset_type)


Evaluator = Callable[[Asset | None, RuleContext], RuleResult]


@dataclass(frozen=True)
class SecurityRule:
    key: str
    version: int
    name: str
    description: str
    service: str
    asset_type: AssetType | None
    category: str
    severity: FindingSeverity
    remediation: str
    references: tuple[str, ...] = field(default_factory=tuple)
    enabled_by_default: bool = True
    additional_asset_types: tuple[AssetType, ...] = field(default_factory=tuple)
    evaluator: Evaluator = field(repr=False, compare=False, default=lambda _a, _c: None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not self.key or self.version <= 0:
            raise ValueError("Rules require a stable key and positive version.")
        if self.asset_type is None and self.additional_asset_types:
            raise ValueError("Account-level rules cannot declare additional asset types.")

    @property
    def asset_types(self) -> tuple[AssetType, ...]:
        if self.asset_type is None:
            return ()
        return (self.asset_type, *self.additional_asset_types)

    def applies_to(self, asset: Asset | None) -> bool:
        if self.asset_type is None:
            return asset is None
        return asset is not None and asset.asset_type in self.asset_types

    def evaluate(self, asset: Asset | None, context: RuleContext) -> RuleResult:
        if not self.applies_to(asset):
            from app.security_rules.results import not_applicable

            return not_applicable("asset_type_mismatch")
        return self.evaluator(asset, context)
