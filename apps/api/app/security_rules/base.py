from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.models import Asset
from app.models.enums import AssetType, FindingSeverity
from app.security_rules.results import RuleResult


@dataclass(frozen=True)
class RuleContext:
    account_assets: tuple[Asset, ...]

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
    evaluator: Evaluator = field(repr=False, compare=False, default=lambda _a, _c: None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not self.key or self.version <= 0:
            raise ValueError("Rules require a stable key and positive version.")

    def evaluate(self, asset: Asset | None, context: RuleContext) -> RuleResult:
        if self.asset_type is not None and (asset is None or asset.asset_type != self.asset_type):
            from app.security_rules.results import not_applicable

            return not_applicable("asset_type_mismatch")
        return self.evaluator(asset, context)
