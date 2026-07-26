from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EvaluationRuleResult
from app.models.enums import (
    AssetType,
    EvaluationJobStatus,
    FindingSeverity,
    RuleResultStatus,
)
from app.schemas.findings import FindingSuppressRequest
from app.security_rules import RuleRegistry, default_registry
from app.security_rules.base import RuleContext, SecurityRule
from app.security_rules.results import error
from app.services.evaluations import EvaluationService
from app.tests.conftest import register_and_login
from app.tests.test_stage4_rules import asset, seeded_account


def test_registry_filters_are_combined_stable_and_do_not_execute_rules() -> None:
    evaluator = Mock(side_effect=AssertionError("metadata listing executed a rule"))
    disabled = SecurityRule(
        "TEST_DISABLED",
        1,
        "Disabled",
        "Disabled test rule",
        "iam",
        AssetType.IAM_ROLE,
        "least_privilege",
        FindingSeverity.HIGH,
        "None",
        enabled_by_default=False,
        evaluator=evaluator,
    )
    registry = RuleRegistry((*default_registry.all(), disabled))

    filtered = registry.filter(
        service="iam",
        asset_type=AssetType.IAM_ROLE,
        severity=FindingSeverity.CRITICAL,
        category="least_privilege",
        enabled=True,
    )
    assert [rule.key for rule in filtered] == [
        "IAM_ADMINISTRATOR_ACCESS_ATTACHED",
        "IAM_INLINE_POLICY_ALLOW_ALL",
    ]
    assert registry.filter(service="does-not-exist") == ()
    assert registry.filter(enabled=False) == (disabled,)
    assert [rule.key for rule in registry.all()] == sorted(rule.key for rule in registry.all())
    evaluator.assert_not_called()


def test_rule_api_filters_and_rejects_unknown_values(client: TestClient) -> None:
    headers = register_and_login(client, "stage4-filter-owner@example.com")
    organization = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "Rule Filters", "slug": f"rule-filters-{uuid.uuid4()}"},
    ).json()
    params = {
        "organization_id": organization["id"],
        "service": "iam",
        "asset_type": "iam_role",
        "category": "least_privilege",
        "severity": "critical",
        "enabled": "true",
    }
    response = client.get("/api/v1/rules", headers=headers, params=params)
    assert response.status_code == 200
    assert [item["key"] for item in response.json()] == [
        "IAM_ADMINISTRATOR_ACCESS_ATTACHED",
        "IAM_INLINE_POLICY_ALLOW_ALL",
    ]
    for name, value in (
        ("service", "unknown"),
        ("asset_type", "unknown"),
        ("category", "unknown"),
        ("severity", "unknown"),
    ):
        invalid = client.get(
            "/api/v1/rules",
            headers=headers,
            params={"organization_id": organization["id"], name: value},
        )
        assert invalid.status_code == 422


@pytest.mark.parametrize(
    "asset_type",
    [AssetType.IAM_USER, AssetType.IAM_ROLE, AssetType.IAM_GROUP],
)
def test_administrator_access_targets_users_roles_and_groups(asset_type: AssetType) -> None:
    rule = default_registry.get("IAM_ADMINISTRATOR_ACCESS_ATTACHED")
    assert rule is not None
    exposed = asset(
        asset_type,
        {"attached_policy_arns": ["arn:aws:iam::aws:policy/AdministratorAccess"]},
    )
    safe = asset(asset_type, {"attached_policy_arns": ["arn:aws:iam::aws:policy/ReadOnlyAccess"]})
    assert rule.evaluate(exposed, RuleContext((exposed,))).status == RuleResultStatus.FAILED
    assert rule.evaluate(safe, RuleContext((safe,))).status == RuleResultStatus.PASSED


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ({"Effect": "Allow", "Action": "*", "Resource": "*"}, RuleResultStatus.FAILED),
        (
            {"Effect": "Allow", "Action": ["s3:GetObject", "*"], "Resource": ["arn:x", "*"]},
            RuleResultStatus.FAILED,
        ),
        (
            {"Effect": "Allow", "Action": "*", "Resource": "arn:aws:s3:::bounded/*"},
            RuleResultStatus.PASSED,
        ),
        ({"Effect": "Allow", "Action": "s3:*", "Resource": "*"}, RuleResultStatus.PASSED),
        ({"Effect": "Deny", "Action": "*", "Resource": "*"}, RuleResultStatus.PASSED),
        ({"Effect": "Allow", "Action": "*"}, RuleResultStatus.ERROR),
    ],
)
@pytest.mark.parametrize(
    "asset_type", [AssetType.IAM_USER, AssetType.IAM_ROLE, AssetType.IAM_GROUP]
)
def test_inline_policy_semantics_for_all_principal_types(
    asset_type: AssetType,
    statement: dict[str, object],
    expected: RuleResultStatus,
) -> None:
    rule = default_registry.get("IAM_INLINE_POLICY_ALLOW_ALL")
    assert rule is not None
    item = asset(asset_type, {"inline_policy_documents": [{"Statement": statement}]})
    first = rule.evaluate(item, RuleContext((item,)))
    second = rule.evaluate(item, RuleContext((item,)))
    assert first.status == expected
    assert first == second


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        (
            {
                "Statement": {
                    "Effect": "Deny",
                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                }
            },
            RuleResultStatus.PASSED,
        ),
        (
            {
                "Statement": [
                    {"Effect": "Allow", "Condition": {"Bool": {"aws:SecureTransport": "false"}}},
                    {
                        "Effect": "Deny",
                        "Condition": {"Bool": {"aws:SecureTransport": False}},
                    },
                ]
            },
            RuleResultStatus.PASSED,
        ),
        (
            {"Statement": {"Effect": "Deny", "Condition": {"Bool": {"unrelated": "false"}}}},
            RuleResultStatus.FAILED,
        ),
        (None, RuleResultStatus.FAILED),
        ({"malformed": True}, RuleResultStatus.ERROR),
    ],
)
def test_s3_https_policy_is_structurally_evaluated(
    document: dict[str, object] | None, expected: RuleResultStatus
) -> None:
    rule = default_registry.get("S3_BUCKET_HTTPS_ONLY_POLICY_MISSING")
    assert rule is not None
    item = asset(AssetType.S3_BUCKET, {"policy_document": document})
    assert rule.evaluate(item, RuleContext((item,))).status == expected


def test_access_key_age_uses_fixed_evaluation_time() -> None:
    rule = default_registry.get("IAM_USER_ACCESS_KEY_TOO_OLD")
    assert rule is not None
    evaluated_at = datetime(2026, 1, 1, tzinfo=UTC)
    item = asset(
        AssetType.IAM_USER,
        {"active_key_created_at": [(evaluated_at - timedelta(days=90)).isoformat()]},
    )
    context = RuleContext((item,), evaluated_at=evaluated_at)
    assert rule.evaluate(item, context).status == RuleResultStatus.PASSED
    item.metadata_json["active_key_created_at"] = [(evaluated_at - timedelta(days=91)).isoformat()]
    assert rule.evaluate(item, context).status == RuleResultStatus.FAILED


def test_past_suppression_expiry_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FindingSuppressRequest(
            reason="Expired maintenance window",
            suppressed_until=datetime.now(UTC) - timedelta(seconds=1),
        )


def test_all_rule_errors_mark_evaluation_failed(db: Session) -> None:
    actor, _organization, account, _item = seeded_account(db)
    broken = SecurityRule(
        "TEST_ALWAYS_ERROR",
        1,
        "Always error",
        "Test rule",
        "ec2",
        AssetType.EC2_SECURITY_GROUP,
        "network",
        FindingSeverity.HIGH,
        "None",
        evaluator=lambda _asset, _context: error("deterministic_test_error"),
    )
    job = EvaluationService(db, RuleRegistry((broken,))).start(account.id, actor)
    assert job.status == EvaluationJobStatus.FAILED
    assert job.evaluation_errors == 1
    assert job.finished_at is not None
    totals = db.execute(
        select(
            func.sum(EvaluationRuleResult.passed_count),
            func.sum(EvaluationRuleResult.failed_count),
            func.sum(EvaluationRuleResult.not_applicable_count),
            func.sum(EvaluationRuleResult.error_count),
        ).where(EvaluationRuleResult.evaluation_job_id == job.id)
    ).one()
    assert tuple(value or 0 for value in totals) == (
        job.passed_count,
        job.failed_count,
        job.not_applicable_count,
        job.error_count,
    )


def test_fatal_repository_failure_cannot_leave_running_job(
    db: Session, caplog: pytest.LogCaptureFixture
) -> None:
    actor, _organization, account, _item = seeded_account(db)
    service = EvaluationService(db)
    cast(Any, service.findings).for_rule = Mock(
        side_effect=RuntimeError("provider secret must not escape")
    )
    with caplog.at_level(logging.INFO, logger="cloudops.security"):
        job = service.start(account.id, actor)
    assert job.status == EvaluationJobStatus.FAILED
    assert job.finished_at is not None
    assert job.error_summary == "evaluation_execution_failed"
    assert "provider secret must not escape" not in caplog.text
