from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from app.models.enums import (
    BusinessImpact,
    DataSensitivity,
    FindingSeverity,
    RiskCriticality,
    RiskEnvironment,
    RiskPriority,
)

POLICY_KEY = "CLOUDOPS_RISK_V1"
POLICY_VERSION = 1

COMPONENT_MAXIMUMS: dict[str, int] = {
    "severity": 30,
    "exposure": 15,
    "exploitability": 10,
    "privilege": 10,
    "asset_criticality": 10,
    "environment": 5,
    "business_impact": 10,
    "data_sensitivity": 5,
    "age": 5,
}

SEVERITY_POINTS = {
    FindingSeverity.CRITICAL: 30,
    FindingSeverity.HIGH: 24,
    FindingSeverity.MEDIUM: 16,
    FindingSeverity.LOW: 8,
    FindingSeverity.INFORMATIONAL: 0,
}
EXPOSURE_POINTS = {
    "public": 15,
    "internet_reachable": 12,
    "internal": 5,
    "none": 0,
    "unknown": 7,
}
EXPLOITABILITY_POINTS = {"high": 10, "medium": 6, "low": 3, "unknown": 5}
# A finding requiring no privilege is easier to exploit and therefore receives more points.
PRIVILEGE_POINTS = {"none": 10, "low": 7, "high": 2, "unknown": 5}
CRITICALITY_POINTS = {
    RiskCriticality.CRITICAL: 10,
    RiskCriticality.HIGH: 8,
    RiskCriticality.MEDIUM: 5,
    RiskCriticality.LOW: 2,
    RiskCriticality.UNKNOWN: 5,
}
ENVIRONMENT_POINTS = {
    RiskEnvironment.PRODUCTION: 5,
    RiskEnvironment.STAGING: 3,
    RiskEnvironment.DEVELOPMENT: 1,
    RiskEnvironment.SANDBOX: 0,
    RiskEnvironment.UNKNOWN: 2,
}
BUSINESS_IMPACT_POINTS = {
    BusinessImpact.CRITICAL: 10,
    BusinessImpact.HIGH: 8,
    BusinessImpact.MEDIUM: 5,
    BusinessImpact.LOW: 2,
    BusinessImpact.UNKNOWN: 5,
}
DATA_SENSITIVITY_POINTS = {
    DataSensitivity.RESTRICTED: 5,
    DataSensitivity.CONFIDENTIAL: 4,
    DataSensitivity.INTERNAL: 2,
    DataSensitivity.PUBLIC: 0,
    DataSensitivity.UNKNOWN: 2,
}

# Trusted, versioned deterministic rule context. Absence means neutral/unknown, never safest.
RULE_CONTEXT: dict[str, tuple[str, str]] = {
    "EC2_SG_SSH_OPEN_TO_WORLD": ("public", "high"),
    "EC2_SG_RDP_OPEN_TO_WORLD": ("public", "high"),
    "EC2_SG_ALL_TRAFFIC_OPEN_TO_WORLD": ("public", "high"),
    "EC2_INSTANCE_PUBLIC_IP": ("public", "medium"),
    "S3_BUCKET_PUBLIC_ACCESS_CONFIRMED": ("public", "high"),
    "RDS_INSTANCE_PUBLICLY_ACCESSIBLE": ("public", "high"),
    "IAM_ADMINISTRATOR_ACCESS_ATTACHED": ("none", "high"),
    "IAM_INLINE_POLICY_ALLOW_ALL": ("none", "high"),
}

POLICY_WEIGHTS = {
    "component_maximums": COMPONENT_MAXIMUMS,
    "severity": {key.value: value for key, value in SEVERITY_POINTS.items()},
    "exposure": EXPOSURE_POINTS,
    "exploitability": EXPLOITABILITY_POINTS,
    "required_privilege": PRIVILEGE_POINTS,
    "asset_criticality": {key.value: value for key, value in CRITICALITY_POINTS.items()},
    "environment": {key.value: value for key, value in ENVIRONMENT_POINTS.items()},
    "business_impact": {key.value: value for key, value in BUSINESS_IMPACT_POINTS.items()},
    "data_sensitivity": {key.value: value for key, value in DATA_SENSITIVITY_POINTS.items()},
    "age_threshold_days": {"0": 0, "7": 1, "30": 3, "90": 4, "180": 5},
    "compensating_control": {"minimum": -15, "maximum": 0},
    "account_aggregate": {"highest": 50, "top_ten_mean": 30, "all_mean": 20},
    "organization_aggregate": {"highest_account": 60, "mean_account": 40},
}
POLICY_BANDS = {
    RiskPriority.LOW.value: [0, 29],
    RiskPriority.MEDIUM.value: [30, 59],
    RiskPriority.HIGH.value: [60, 79],
    RiskPriority.CRITICAL.value: [80, 100],
}


@dataclass(frozen=True)
class RiskInputs:
    severity: FindingSeverity
    rule_key: str
    first_seen_at: datetime
    evaluation_time: datetime
    criticality: RiskCriticality = RiskCriticality.UNKNOWN
    environment: RiskEnvironment = RiskEnvironment.UNKNOWN
    business_impact: BusinessImpact = BusinessImpact.UNKNOWN
    data_sensitivity: DataSensitivity = DataSensitivity.UNKNOWN
    exposure: str | None = None
    exploitability: str | None = None
    required_privilege: str | None = None
    compensating_adjustment: int = 0


@dataclass(frozen=True)
class RiskResult:
    score: int
    priority: RiskPriority
    components: Mapping[str, int]
    explanation_codes: Mapping[str, str]
    unknown_inputs: tuple[str, ...]


@dataclass(frozen=True)
class AggregateRisk:
    score: int
    priority: RiskPriority
    highest: int
    focused_mean: int
    overall_mean: int
    reason_code: str


def clamp(value: int, minimum: int = 0, maximum: int = 100) -> int:
    return min(maximum, max(minimum, value))


def priority_for_score(score: int) -> RiskPriority:
    checked = clamp(score)
    if checked >= 80:
        return RiskPriority.CRITICAL
    if checked >= 60:
        return RiskPriority.HIGH
    if checked >= 30:
        return RiskPriority.MEDIUM
    return RiskPriority.LOW


def age_points(first_seen_at: datetime, evaluation_time: datetime) -> tuple[int, str]:
    first = _aware(first_seen_at)
    evaluated = _aware(evaluation_time)
    days = max(0, (evaluated - first).days)
    if days >= 180:
        return 5, "age_180_plus_days"
    if days >= 90:
        return 4, "age_90_179_days"
    if days >= 30:
        return 3, "age_30_89_days"
    if days >= 7:
        return 1, "age_7_29_days"
    return 0, "age_under_7_days"


def score_finding(inputs: RiskInputs) -> RiskResult:
    context_exposure, context_exploitability = RULE_CONTEXT.get(
        inputs.rule_key, ("unknown", "unknown")
    )
    exposure = _known(inputs.exposure, EXPOSURE_POINTS, context_exposure)
    exploitability = _known(inputs.exploitability, EXPLOITABILITY_POINTS, context_exploitability)
    privilege = _known(inputs.required_privilege, PRIVILEGE_POINTS, "unknown")
    adjustment = min(0, max(-15, inputs.compensating_adjustment))
    age_value, age_code = age_points(inputs.first_seen_at, inputs.evaluation_time)
    components = {
        "severity": SEVERITY_POINTS[inputs.severity],
        "exposure": EXPOSURE_POINTS[exposure],
        "exploitability": EXPLOITABILITY_POINTS[exploitability],
        "privilege": PRIVILEGE_POINTS[privilege],
        "asset_criticality": CRITICALITY_POINTS[inputs.criticality],
        "environment": ENVIRONMENT_POINTS[inputs.environment],
        "business_impact": BUSINESS_IMPACT_POINTS[inputs.business_impact],
        "data_sensitivity": DATA_SENSITIVITY_POINTS[inputs.data_sensitivity],
        "age": age_value,
        "compensating_controls": adjustment,
    }
    total = clamp(sum(components.values()))
    unknown: list[str] = []
    for name, value in (
        ("exposure", exposure),
        ("exploitability", exploitability),
        ("required_privilege", privilege),
        ("asset_criticality", inputs.criticality.value),
        ("environment", inputs.environment.value),
        ("business_impact", inputs.business_impact.value),
        ("data_sensitivity", inputs.data_sensitivity.value),
    ):
        if value == "unknown":
            unknown.append(name)
    explanations = {
        "severity": f"severity_{inputs.severity.value}",
        "exposure": f"exposure_{exposure}",
        "exploitability": f"exploitability_{exploitability}",
        "privilege": f"privilege_{privilege}",
        "asset_criticality": f"criticality_{inputs.criticality.value}",
        "environment": f"environment_{inputs.environment.value}",
        "business_impact": f"business_impact_{inputs.business_impact.value}",
        "data_sensitivity": f"data_sensitivity_{inputs.data_sensitivity.value}",
        "age": age_code,
        "compensating_controls": (
            "compensating_control_applied" if adjustment else "no_compensating_control"
        ),
    }
    return RiskResult(
        score=total,
        priority=priority_for_score(total),
        components=components,
        explanation_codes=explanations,
        unknown_inputs=tuple(unknown),
    )


def account_risk(scores: Sequence[int]) -> AggregateRisk:
    if not scores:
        return AggregateRisk(0, RiskPriority.LOW, 0, 0, 0, "no_active_findings")
    ordered = sorted((clamp(score) for score in scores), reverse=True)
    highest = ordered[0]
    top_ten_mean = _mean(ordered[:10])
    all_mean = _mean(ordered)
    score = _weighted((highest, 50), (top_ten_mean, 30), (all_mean, 20))
    return AggregateRisk(
        score,
        priority_for_score(score),
        highest,
        top_ten_mean,
        all_mean,
        "active_findings_scored",
    )


def organization_risk(account_scores: Sequence[int]) -> AggregateRisk:
    if not account_scores:
        return AggregateRisk(0, RiskPriority.LOW, 0, 0, 0, "no_accounts_scored")
    checked = [clamp(score) for score in account_scores]
    highest = max(checked)
    mean = _mean(checked)
    score = _weighted((highest, 60), (mean, 40))
    return AggregateRisk(
        score,
        priority_for_score(score),
        highest,
        mean,
        mean,
        "account_risk_aggregated",
    )


def _mean(values: Sequence[int]) -> int:
    if not values:
        return 0
    return _round_decimal(Decimal(sum(values)) / Decimal(len(values)))


def _weighted(*parts: tuple[int, int]) -> int:
    return clamp(
        _round_decimal(
            sum((Decimal(value) * Decimal(weight) for value, weight in parts), Decimal())
            / Decimal(100)
        )
    )


def _round_decimal(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _known(value: str | None, mapping: Mapping[str, int], fallback: str) -> str:
    normalized = value.strip().casefold() if value else fallback
    return normalized if normalized in mapping else "unknown"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
