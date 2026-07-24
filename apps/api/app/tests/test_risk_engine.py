from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.enums import (
    BusinessImpact,
    DataSensitivity,
    FindingSeverity,
    RiskCriticality,
    RiskEnvironment,
    RiskPriority,
)
from app.risk_engine import (
    RiskInputs,
    account_risk,
    age_points,
    organization_risk,
    priority_for_score,
    score_finding,
)


@pytest.mark.parametrize(
    ("score", "priority"),
    [
        (0, RiskPriority.LOW),
        (29, RiskPriority.LOW),
        (30, RiskPriority.MEDIUM),
        (59, RiskPriority.MEDIUM),
        (60, RiskPriority.HIGH),
        (79, RiskPriority.HIGH),
        (80, RiskPriority.CRITICAL),
        (100, RiskPriority.CRITICAL),
    ],
)
def test_priority_boundaries(score: int, priority: RiskPriority) -> None:
    assert priority_for_score(score) == priority


@pytest.mark.parametrize(
    ("days", "points"),
    [(0, 0), (6, 0), (7, 1), (29, 1), (30, 3), (89, 3), (90, 4), (179, 4), (180, 5)],
)
def test_age_thresholds_use_one_fixed_evaluation_time(days: int, points: int) -> None:
    evaluated = datetime(2026, 7, 24, tzinfo=UTC)
    assert age_points(evaluated - timedelta(days=days), evaluated)[0] == points


def test_component_mapping_unknowns_and_determinism() -> None:
    evaluated = datetime(2026, 7, 24, tzinfo=UTC)
    inputs = RiskInputs(
        severity=FindingSeverity.HIGH,
        rule_key="UNKNOWN_RULE",
        first_seen_at=evaluated - timedelta(days=31),
        evaluation_time=evaluated,
    )
    first = score_finding(inputs)
    second = score_finding(inputs)
    assert first == second
    assert first.components == {
        "severity": 24,
        "exposure": 7,
        "exploitability": 5,
        "privilege": 5,
        "asset_criticality": 5,
        "environment": 2,
        "business_impact": 5,
        "data_sensitivity": 2,
        "age": 3,
        "compensating_controls": 0,
    }
    assert set(first.unknown_inputs) == {
        "exposure",
        "exploitability",
        "required_privilege",
        "asset_criticality",
        "environment",
        "business_impact",
        "data_sensitivity",
    }


def test_maximum_clamping_and_compensating_control_limit() -> None:
    evaluated = datetime(2026, 7, 24, tzinfo=UTC)
    maximum = score_finding(
        RiskInputs(
            severity=FindingSeverity.CRITICAL,
            rule_key="EC2_SG_ALL_TRAFFIC_OPEN_TO_WORLD",
            first_seen_at=evaluated - timedelta(days=365),
            evaluation_time=evaluated,
            criticality=RiskCriticality.CRITICAL,
            environment=RiskEnvironment.PRODUCTION,
            business_impact=BusinessImpact.CRITICAL,
            data_sensitivity=DataSensitivity.RESTRICTED,
            required_privilege="none",
        )
    )
    assert maximum.score == 100
    assert maximum.priority == RiskPriority.CRITICAL
    reduced = score_finding(
        RiskInputs(
            severity=FindingSeverity.CRITICAL,
            rule_key="EC2_SG_ALL_TRAFFIC_OPEN_TO_WORLD",
            first_seen_at=evaluated - timedelta(days=365),
            evaluation_time=evaluated,
            criticality=RiskCriticality.CRITICAL,
            environment=RiskEnvironment.PRODUCTION,
            business_impact=BusinessImpact.CRITICAL,
            data_sensitivity=DataSensitivity.RESTRICTED,
            required_privilege="none",
            compensating_adjustment=-99,
        )
    )
    assert reduced.components["compensating_controls"] == -15
    assert reduced.score == 85


def test_minimum_score_and_unknown_is_not_zero() -> None:
    evaluated = datetime(2026, 7, 24, tzinfo=UTC)
    explicit_minimum = score_finding(
        RiskInputs(
            severity=FindingSeverity.INFORMATIONAL,
            rule_key="UNKNOWN_RULE",
            first_seen_at=evaluated,
            evaluation_time=evaluated,
            criticality=RiskCriticality.LOW,
            environment=RiskEnvironment.SANDBOX,
            business_impact=BusinessImpact.LOW,
            data_sensitivity=DataSensitivity.PUBLIC,
            exposure="none",
            exploitability="low",
            required_privilege="high",
            compensating_adjustment=-15,
        )
    )
    assert explicit_minimum.score == 0
    unknown = score_finding(
        RiskInputs(
            severity=FindingSeverity.INFORMATIONAL,
            rule_key="UNKNOWN_RULE",
            first_seen_at=evaluated,
            evaluation_time=evaluated,
        )
    )
    assert unknown.score > 0


def test_aggregate_formulas_empty_one_and_more_than_ten() -> None:
    empty = account_risk([])
    assert empty.score == 0
    assert empty.reason_code == "no_active_findings"
    one = account_risk([80])
    assert one.score == 80
    values = list(range(100, 88, -1))
    aggregate = account_risk(values)
    assert aggregate.highest == 100
    assert aggregate.focused_mean == 96
    assert aggregate.overall_mean == 95
    assert aggregate.score == 98
    organization = organization_risk([80, 40])
    assert organization.highest == 80
    assert organization.focused_mean == 60
    assert organization.score == 72
