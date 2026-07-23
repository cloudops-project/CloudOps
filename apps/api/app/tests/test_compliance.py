from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ComplianceAssessment,
    ComplianceAssessmentControl,
    EvaluationRuleResult,
    Finding,
    RuleControlMapping,
)
from app.models.enums import ComplianceControlStatus, FindingSeverity, FindingStatus
from app.services.compliance import ComplianceService
from app.tests.conftest import register_and_login


def _organization(client: TestClient) -> tuple[dict[str, str], str]:
    headers = register_and_login(client, "compliance-owner@example.com")
    response = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "Compliance Org", "slug": "compliance-org"},
    )
    assert response.status_code == 201, response.text
    return headers, cast(str, response.json()["id"])


def _account(client: TestClient, headers: dict[str, str], organization_id: str) -> dict[str, Any]:
    response = client.post(
        "/api/v1/aws/accounts",
        headers=headers,
        json={
            "organization_id": organization_id,
            "name": "Compliance account",
            "account_id": "123456789012",
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def test_catalog_is_versioned_and_requires_organization_read_access(client: TestClient) -> None:
    headers, organization_id = _organization(client)
    response = client.get(
        "/api/v1/compliance/frameworks",
        headers=headers,
        params={"organization_id": organization_id},
    )
    assert response.status_code == 200, response.text
    frameworks = response.json()
    assert {item["key"] for item in frameworks} == {
        "cis_aws",
        "nist_csf",
        "iso_27001",
        "pci_dss",
    }
    assert all(item["version"] and item["official_reference"] for item in frameworks)


def test_assessment_without_complete_evaluation_never_marks_control_pass(
    client: TestClient, db: Session
) -> None:
    headers, organization_id = _organization(client)
    account = _account(client, headers, organization_id)
    response = client.post(
        f"/api/v1/aws/accounts/{account['account']['id']}/compliance/assess",
        headers=headers,
        json={"framework_key": "cis_aws"},
    )
    assert response.status_code == 201, response.text
    assessment = db.scalar(select(ComplianceAssessment))
    assert assessment is not None
    snapshots = list(
        db.scalars(
            select(ComplianceAssessmentControl).where(
                ComplianceAssessmentControl.assessment_id == assessment.id
            )
        ).all()
    )
    assert snapshots
    assert {item.status for item in snapshots} == {ComplianceControlStatus.NOT_ASSESSED}
    assert assessment.controls_passed == 0


def test_assessment_list_is_tenant_scoped(client: TestClient) -> None:
    first_headers, first_organization_id = _organization(client)
    first_account = _account(client, first_headers, first_organization_id)
    assert (
        client.post(
            f"/api/v1/aws/accounts/{first_account['account']['id']}/compliance/assess",
            headers=first_headers,
            json={"framework_key": "cis_aws"},
        ).status_code
        == 201
    )

    second_headers = register_and_login(client, "compliance-second@example.com")
    second_organization = client.post(
        "/api/v1/organizations",
        headers=second_headers,
        json={"name": "Second compliance", "slug": "second-compliance"},
    ).json()["id"]
    response = client.get(
        "/api/v1/compliance/assessments",
        headers=second_headers,
        params={"organization_id": second_organization},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_summary_and_control_detail_are_tenant_scoped(client: TestClient) -> None:
    headers, organization_id = _organization(client)
    frameworks = client.get(
        "/api/v1/compliance/frameworks",
        headers=headers,
        params={"organization_id": organization_id},
    ).json()
    controls = client.get(
        f"/api/v1/compliance/frameworks/{frameworks[0]['key']}/controls",
        headers=headers,
        params={"organization_id": organization_id},
    ).json()
    detail = client.get(
        f"/api/v1/compliance/controls/{controls[0]['id']}",
        headers=headers,
        params={"organization_id": organization_id},
    )
    summary = client.get(
        "/api/v1/compliance/summary",
        headers=headers,
        params={"organization_id": organization_id},
    )
    assert detail.status_code == 200
    assert summary.status_code == 200
    assert summary.json()["assessments_total"] == 0


def test_control_semantics_require_matching_successful_rule_results() -> None:
    framework_id = uuid.uuid4()
    control_id = uuid.uuid4()
    mapping = RuleControlMapping(
        rule_key="TEST_RULE",
        minimum_rule_version=2,
        maximum_rule_version=3,
        framework_id=framework_id,
        control_id=control_id,
        rationale="Version-aware deterministic mapping.",
    )
    successful = EvaluationRuleResult(
        evaluation_job_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        aws_account_id=uuid.uuid4(),
        rule_key="TEST_RULE",
        rule_version=2,
        passed_count=1,
        failed_count=0,
        not_applicable_count=0,
        error_count=0,
    )
    assert (
        ComplianceService._control_status(
            mappings=[mapping],
            findings=[],
            source_state=ComplianceControlStatus.PASS,
            rule_results=[successful],
        )
        == ComplianceControlStatus.PASS
    )

    successful.rule_version = 4
    assert (
        ComplianceService._control_status(
            mappings=[mapping],
            findings=[],
            source_state=ComplianceControlStatus.PASS,
            rule_results=[successful],
        )
        == ComplianceControlStatus.NOT_ASSESSED
    )


def test_control_semantics_never_turn_rule_error_into_pass() -> None:
    mapping = RuleControlMapping(
        rule_key="ERROR_RULE",
        minimum_rule_version=1,
        framework_id=uuid.uuid4(),
        control_id=uuid.uuid4(),
        rationale="Error mapping.",
    )
    errored = EvaluationRuleResult(
        evaluation_job_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        aws_account_id=uuid.uuid4(),
        rule_key="ERROR_RULE",
        rule_version=1,
        passed_count=0,
        failed_count=0,
        not_applicable_count=0,
        error_count=1,
    )
    assert (
        ComplianceService._control_status(
            mappings=[mapping],
            findings=[],
            source_state=ComplianceControlStatus.PASS,
            rule_results=[errored],
        )
        == ComplianceControlStatus.ERROR
    )


def test_legacy_evaluation_without_rule_summaries_is_not_assessed() -> None:
    mapping = RuleControlMapping(
        rule_key="LEGACY_RULE",
        minimum_rule_version=1,
        framework_id=uuid.uuid4(),
        control_id=uuid.uuid4(),
        rationale="Legacy evidence must not fabricate a pass.",
    )
    assert (
        ComplianceService._control_status(
            mappings=[mapping],
            findings=[],
            source_state=ComplianceControlStatus.PASS,
            rule_results=[],
        )
        == ComplianceControlStatus.NOT_ASSESSED
    )


def test_suppressed_finding_remains_a_control_failure() -> None:
    organization_id = uuid.uuid4()
    account_id = uuid.uuid4()
    evaluation_id = uuid.uuid4()
    now = datetime.now(UTC)
    mapping = RuleControlMapping(
        rule_key="SUPPRESSED_RULE",
        minimum_rule_version=1,
        framework_id=uuid.uuid4(),
        control_id=uuid.uuid4(),
        rationale="Suppression accepts risk but does not prove compliance.",
    )
    finding = Finding(
        organization_id=organization_id,
        aws_account_id=account_id,
        rule_key="SUPPRESSED_RULE",
        rule_version=1,
        severity=FindingSeverity.HIGH,
        category="test",
        status=FindingStatus.SUPPRESSED,
        evidence_json={},
        first_seen_at=now,
        last_seen_at=now,
        suppressed_at=now,
        suppression_reason="Accepted for testing.",
        suppressed_by_user_id=uuid.uuid4(),
        last_evaluation_id=evaluation_id,
    )
    assert (
        ComplianceService._control_status(
            mappings=[mapping],
            findings=[finding],
            source_state=ComplianceControlStatus.PASS,
            rule_results=[],
        )
        == ComplianceControlStatus.FAIL
    )


@pytest.mark.parametrize(
    "rule_version,expected",
    [
        (1, ComplianceControlStatus.NOT_ASSESSED),
        (2, ComplianceControlStatus.PASS),
        (3, ComplianceControlStatus.PASS),
        (4, ComplianceControlStatus.PASS),
        (5, ComplianceControlStatus.PASS),
        (6, ComplianceControlStatus.NOT_ASSESSED),
    ],
)
def test_overlapping_mapping_ranges_use_deterministic_union_semantics(
    rule_version: int, expected: ComplianceControlStatus
) -> None:
    framework_id = uuid.uuid4()
    control_id = uuid.uuid4()
    mappings = [
        RuleControlMapping(
            rule_key="RANGE_RULE",
            minimum_rule_version=2,
            maximum_rule_version=4,
            framework_id=framework_id,
            control_id=control_id,
            rationale="First accepted range.",
        ),
        RuleControlMapping(
            rule_key="RANGE_RULE",
            minimum_rule_version=4,
            maximum_rule_version=5,
            framework_id=framework_id,
            control_id=control_id,
            rationale="Overlapping accepted range.",
        ),
    ]
    result = EvaluationRuleResult(
        evaluation_job_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        aws_account_id=uuid.uuid4(),
        rule_key="RANGE_RULE",
        rule_version=rule_version,
        passed_count=1,
        failed_count=0,
        not_applicable_count=0,
        error_count=0,
    )
    assert (
        ComplianceService._control_status(
            mappings=mappings,
            findings=[],
            source_state=ComplianceControlStatus.PASS,
            rule_results=[result],
        )
        == expected
    )
