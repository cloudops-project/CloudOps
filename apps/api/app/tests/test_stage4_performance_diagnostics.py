from __future__ import annotations

import statistics
import time
import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Asset, AWSAccount, User
from app.models.enums import AssetType, AWSAccountStatus
from app.security_rules import default_registry
from app.security_rules.base import RuleContext
from app.services.common import now_utc
from app.tests.conftest import TestingSession, register_and_login
from app.tests.test_stage4_rules import asset
from app.worker.job_worker import JobWorker


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * percentile))]


def test_stage4_local_performance_and_query_diagnostics(
    client: TestClient, db: Session, capsys: Any
) -> None:
    synthetic = tuple(
        asset(
            AssetType.EC2_SECURITY_GROUP,
            {
                "ip_permissions": [
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 22,
                        "ToPort": 22,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0" if index % 2 else "10.0.0.0/8"}],
                    }
                ]
            },
        )
        for index in range(500)
    )
    context = RuleContext(synthetic, evaluated_at=now_utc())
    rules = default_registry.filter(
        service="ec2", asset_type=AssetType.EC2_SECURITY_GROUP, enabled=True
    )
    started = time.perf_counter()
    results = [rule.evaluate(item, context) for item in synthetic for rule in rules]
    elapsed = time.perf_counter() - started
    rate = len(results) / max(elapsed, 0.000001)
    assert len(results) == 1500
    assert rate > 100

    headers = register_and_login(client, "stage4-performance@example.com")
    organization = client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "Performance", "slug": f"performance-{uuid.uuid4()}"},
    ).json()
    user = db.scalar(select(User).where(User.normalized_email == "stage4-performance@example.com"))
    assert user is not None
    account = AWSAccount(
        organization_id=uuid.UUID(organization["id"]),
        name="Performance",
        account_id="567890123456",
        role_arn="arn:aws:iam::567890123456:role/CloudOpsReadOnlyRole",
        external_id=f"cloudops-{uuid.uuid4()}",
        status=AWSAccountStatus.CONNECTED,
        connection_status=AWSAccountStatus.CONNECTED,
        created_by_user_id=user.id,
    )
    db.add(account)
    db.flush()
    item = Asset(
        organization_id=uuid.UUID(organization["id"]),
        aws_account_id=account.id,
        asset_type=AssetType.EC2_SECURITY_GROUP,
        resource_id="sg-performance",
        name="performance",
        region="us-east-1",
        tags={},
        metadata_json=synthetic[1].metadata_json,
        first_seen_at=now_utc(),
        last_seen_at=now_utc(),
    )
    db.add(item)
    db.commit()
    evaluated = client.post(f"/api/v1/aws/accounts/{account.id}/evaluate", headers=headers, json={})
    assert evaluated.status_code == 202
    assert JobWorker(TestingSession, get_settings(), "performance-test").process_one()
    finding_id = client.get(
        "/api/v1/findings",
        headers=headers,
        params={"organization_id": organization["id"]},
    ).json()["items"][0]["id"]

    endpoints = {
        "finding_list": (
            "/api/v1/findings",
            {"organization_id": organization["id"], "page_size": 25},
        ),
        "finding_detail": (
            f"/api/v1/findings/{finding_id}",
            {"organization_id": organization["id"]},
        ),
        "finding_summary": (
            "/api/v1/findings/summary",
            {"organization_id": organization["id"]},
        ),
        "rule_list": (
            "/api/v1/rules",
            {"organization_id": organization["id"]},
        ),
    }
    engine = db.get_bind()
    query_count = 0

    def count_query(*_args: Any, **_kwargs: Any) -> None:
        nonlocal query_count
        query_count += 1

    event.listen(engine, "before_cursor_execute", count_query)
    diagnostics: dict[str, dict[str, float | int]] = {}
    try:
        for name, (path, params) in endpoints.items():
            timings: list[float] = []
            counts: list[int] = []
            for _ in range(15):
                query_count = 0
                start = time.perf_counter()
                response = client.get(path, headers=headers, params=params)
                timings.append((time.perf_counter() - start) * 1000)
                counts.append(query_count)
                assert response.status_code == 200
            diagnostics[name] = {
                "median_ms": round(statistics.median(timings), 3),
                "p95_ms": round(_percentile(timings, 0.95), 3),
                "max_queries": max(counts),
            }
            assert max(counts) <= 8
    finally:
        event.remove(engine, "before_cursor_execute", count_query)

    max_evidence_bytes = max(len(str(result.evidence).encode("utf-8")) for result in results)
    assert max_evidence_bytes < 10_000
    with capsys.disabled():
        print(
            "STAGE4_LOCAL_DIAGNOSTICS",
            {
                "assets": len(synthetic),
                "rule_evaluations": len(results),
                "rules_per_second": round(rate, 2),
                "max_evidence_bytes": max_evidence_bytes,
                "endpoints": diagnostics,
            },
        )
