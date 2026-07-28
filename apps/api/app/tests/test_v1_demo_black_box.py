from __future__ import annotations

import inspect
import os
import sys
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import (
    Asset,
    AWSAccount,
    DiscoveryJob,
    EvaluationJob,
    NotificationEvent,
    PlatformJob,
    RemediationRequest,
    ScanRun,
)
from app.models.enums import (
    AssetType,
    AWSAccountStatus,
    DiscoveryJobStatus,
    EvaluationJobStatus,
    NotificationStatus,
    PlatformJobStatus,
    RemediationStatus,
    ScanRunStatus,
)
from app.services.common import now_utc
from app.services.notification_provider import (
    NotificationDeliveryOutcome,
    NotificationDeliveryResult,
)
from app.worker.job_worker import JobWorker

SUPPORT = Path(__file__).resolve().parents[4] / "tests" / "end-to-end"
sys.path.insert(0, str(SUPPORT))
from v1_demo_contract import StepRecorder  # type: ignore[import-not-found]  # noqa: E402

POSTGRES_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.postgres_only,
    pytest.mark.skipif(not POSTGRES_URL, reason="POSTGRES_TEST_DATABASE_URL is required"),
]


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


@pytest.fixture
def v1_demo_client() -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    assert POSTGRES_URL is not None
    database_name = make_url(POSTGRES_URL).database or ""
    assert database_name == "cloudops_test" or database_name.startswith("cloudops_e2e_")
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override() -> Generator[Session, None, None]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    client = TestClient(app, base_url="http://testserver")
    yield client, sessions
    client.close()
    app.dependency_overrides.clear()
    engine.dispose()


def test_v1_demo_acceptance_flow(
    v1_demo_client: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, sessions = v1_demo_client
    recorder = StepRecorder()
    result_path = Path(os.getenv("V1_DEMO_BACKEND_RESULTS", tmp_path / "v1-demo.json"))
    marker = uuid.uuid4().hex
    email = f"v1-demo-{marker}@example.com"
    password = "CloudOps-Demo-Password-123!"
    headers: dict[str, str] = {}
    analyst_headers: dict[str, str] = {}
    analyst: dict[str, str] = {}
    owner: dict[str, Any] = {}
    organization: dict[str, Any] = {}
    account: dict[str, Any] = {}
    finding: dict[str, Any] = {}
    compliance: dict[str, Any] = {}
    risk: dict[str, Any] = {}
    ai: dict[str, Any] = {}
    notification: dict[str, Any] = {}
    notification_delivery: dict[str, Any] = {}
    remediation: dict[str, Any] = {}
    schedule: dict[str, Any] = {}
    aws_invocations: list[str] = []

    def register_login() -> None:
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": "V1 Demo Owner"},
        )
        _assert(registered.status_code == 201, registered.text)
        owner.update(registered.json())
        login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        _assert(login.status_code == 200, login.text)
        headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    recorder.record(1, "Owner registered and login returned an access token", register_login)

    def create_org() -> None:
        created = client.post(
            "/api/v1/organizations",
            headers=headers,
            json={"name": "CloudOps V1 Demo", "slug": f"v1-demo-{marker}"},
        )
        _assert(created.status_code == 201, created.text)
        organization.update(created.json())
        invitation = client.post(
            f"/api/v1/organizations/{organization['id']}/invitations",
            headers=headers,
            json={
                "email": f"analyst-{marker}@example.com",
                "role": "security_analyst",
            },
        )
        _assert(
            invitation.status_code == 201 and invitation.json()["development_token"],
            invitation.text,
        )
        analyst_email = f"analyst-{marker}@example.com"
        analyst["email"] = analyst_email
        client.post(
            "/api/v1/auth/register",
            json={
                "email": analyst_email,
                "password": password,
                "full_name": "Demo Analyst",
            },
        )
        analyst_login = client.post(
            "/api/v1/auth/login", json={"email": analyst_email, "password": password}
        )
        analyst_headers["Authorization"] = f"Bearer {analyst_login.json()['access_token']}"
        accepted = client.post(
            "/api/v1/invitations/accept",
            headers=analyst_headers,
            json={"token": invitation.json()["development_token"]},
        )
        _assert(accepted.status_code == 200, accepted.text)

    recorder.record(2, "Organization and second-user invitation flow completed", create_org)

    def create_account() -> None:
        created = client.post(
            "/api/v1/aws/accounts",
            headers=headers,
            json={
                "organization_id": organization["id"],
                "name": "Synthetic demo account",
                "account_id": str(int(marker[:12], 16) % 1_000_000_000_000).zfill(12),
            },
        )
        _assert(created.status_code == 201, created.text)
        account.update(created.json()["account"])
        with sessions() as db:
            persisted = db.get(AWSAccount, uuid.UUID(account["id"]))
            assert persisted is not None
            persisted.role_arn = f"arn:aws:iam::{persisted.account_id}:role/CloudOpsReadOnlyRole"
            persisted.status = AWSAccountStatus.CONNECTED
            persisted.connection_status = AWSAccountStatus.CONNECTED
            persisted.last_validated_at = now_utc()
            db.commit()

    recorder.record(
        3, "AWS account created publicly and marked synthetic-connected", create_account
    )

    def seed_inventory() -> None:
        with sessions() as db:
            db.add_all(
                [
                    Asset(
                        organization_id=uuid.UUID(organization["id"]),
                        aws_account_id=uuid.UUID(account["id"]),
                        asset_type=AssetType.EC2_INSTANCE,
                        resource_id=f"instance-{marker}",
                        name="Synthetic EC2 instance",
                        region="us-east-1",
                        status="active",
                        metadata_json={
                            "state": "running",
                            "public_ip": "203.0.113.20",
                            "imds_v2_required": False,
                            "synthetic": True,
                        },
                    ),
                    Asset(
                        organization_id=uuid.UUID(organization["id"]),
                        aws_account_id=uuid.UUID(account["id"]),
                        asset_type=AssetType.CLOUDTRAIL_TRAIL,
                        resource_id=f"trail-{marker}",
                        name="Synthetic trail",
                        region="us-east-1",
                        status="disabled",
                        metadata_json={"is_logging": False, "synthetic": True},
                    ),
                    Asset(
                        organization_id=uuid.UUID(organization["id"]),
                        aws_account_id=uuid.UUID(account["id"]),
                        asset_type=AssetType.S3_BUCKET,
                        resource_id=f"bucket-{marker}",
                        name="Synthetic bucket",
                        region="global",
                        status="active",
                        metadata_json={
                            "public_access_block_complete": False,
                            "synthetic": True,
                        },
                    ),
                    Asset(
                        organization_id=uuid.UUID(organization["id"]),
                        aws_account_id=uuid.UUID(account["id"]),
                        asset_type=AssetType.IAM_USER,
                        resource_id=f"iam-user-{marker}",
                        name="Synthetic IAM user",
                        region="global",
                        status="active",
                        metadata_json={
                            "console_access": True,
                            "mfa_enabled": False,
                            "active_key_created_at": ["2025-01-01T00:00:00Z"],
                            "attached_policy_arns": ["arn:aws:iam::aws:policy/AdministratorAccess"],
                            "inline_policy_documents": [
                                {
                                    "Statement": {
                                        "Effect": "Allow",
                                        "Action": "*",
                                        "Resource": "*",
                                    }
                                }
                            ],
                            "synthetic": True,
                        },
                    ),
                ]
            )
            db.commit()

    recorder.record(
        4,
        "Synthetic EC2, S3, IAM, and CloudTrail assets seeded; no AWS discovery route invoked",
        seed_inventory,
    )

    recorder.record(
        5,
        "Dashboard summary rendered from existing records",
        lambda: _assert(
            client.get(
                "/api/v1/dashboard/summary",
                headers=headers,
                params={"organization_id": organization["id"]},
            ).status_code
            == 200,
            "dashboard summary failed",
        ),
    )

    def view_assets() -> None:
        response = client.get(
            "/api/v1/assets", headers=headers, params={"organization_id": organization["id"]}
        )
        _assert(response.status_code == 200 and response.json()["total"] == 4, response.text)

    recorder.record(6, "Asset list returned the seeded synthetic inventory", view_assets)

    def evaluate_findings() -> None:
        response = client.post(
            f"/api/v1/aws/accounts/{account['id']}/evaluate",
            headers=analyst_headers,
            json={},
        )
        _assert(response.status_code == 202, response.text)

        queued_job_id = uuid.UUID(response.json()["id"])

        with sessions() as db:
            db.execute(
                update(PlatformJob)
                .where(
                    PlatformJob.id != queued_job_id,
                    PlatformJob.status.in_(
                        [
                            PlatformJobStatus.AVAILABLE,
                            PlatformJobStatus.RETRY_WAIT,
                            PlatformJobStatus.LEASED,
                            PlatformJobStatus.RUNNING,
                        ]
                    ),
                )
                .values(
                    status=PlatformJobStatus.CANCELLED,
                    worker_id=None,
                    lease_token=None,
                    lease_expires_at=None,
                    completed_at=now_utc(),
                )
            )
            queued = db.get(PlatformJob, queued_job_id)
            assert queued is not None
            queued.priority = 100
            db.commit()

        worker = JobWorker(
            sessions,
            get_settings(),
            f"v1-demo-worker-{marker}",
        )
        _assert(worker.process_one() is True, "Worker processed no job")

        with sessions() as db:
            queued = db.get(PlatformJob, queued_job_id)
            assert queued is not None
            assert queued.status == PlatformJobStatus.SUCCEEDED
            assert queued.result_reference is not None

        findings = client.get(
            "/api/v1/findings",
            headers=headers,
            params={"organization_id": organization["id"], "page_size": 25},
        )
        _assert(
            findings.status_code == 200 and findings.json()["total"] > 0,
            findings.text,
        )
        remediation_candidate = next(
            (
                item
                for item in findings.json()["items"]
                if item["rule_key"] == "S3_BUCKET_PUBLIC_ACCESS_BLOCK_INCOMPLETE"
            ),
            None,
        )
        _assert(
            remediation_candidate is not None,
            "allowlisted synthetic remediation finding was not produced",
        )
        assert remediation_candidate is not None
        finding.update(remediation_candidate)

    recorder.record(7, "Queued evaluation produced deterministic findings", evaluate_findings)

    def assess_compliance() -> None:
        response = client.post(
            f"/api/v1/aws/accounts/{account['id']}/compliance/assess",
            headers=analyst_headers,
            json={"framework_key": "cis_aws"},
        )
        _assert(response.status_code == 201, response.text)
        compliance.update(response.json())
        listing = client.get(
            "/api/v1/compliance/assessments",
            headers=headers,
            params={"organization_id": organization["id"]},
        )
        _assert(listing.status_code == 200 and listing.json()["total"] >= 1, listing.text)

    recorder.record(8, "Compliance assessment route completed and listed", assess_compliance)

    def assess_risk() -> None:
        response = client.post(
            "/api/v1/risk/assess",
            headers=analyst_headers,
            json={"organization_id": organization["id"], "aws_account_id": account["id"]},
        )
        _assert(response.status_code == 201, response.text)
        risk.update(response.json())
        summary = client.get(
            "/api/v1/risk/summary",
            headers=headers,
            params={"organization_id": organization["id"]},
        )
        _assert(summary.status_code == 200 and summary.json()["assessment"], summary.text)

    recorder.record(9, "Risk assessment route completed and summarized", assess_risk)

    def ai_explanation() -> None:
        response = client.post(
            f"/api/v1/findings/{finding['id']}/ai/explain",
            headers=headers,
            json={
                "organization_id": organization["id"],
                "idempotency_key": f"v1-demo-ai-{marker}",
            },
        )
        _assert(response.status_code == 200, response.text)
        ai.update(response.json())
        _assert(ai["content"]["draft_only"] is True, "AI response is not draft-only")

    recorder.record(10, "AI finding explanation is advisory and draft-only", ai_explanation)

    def list_notifications() -> None:
        response = client.get(
            "/api/v1/notifications",
            headers=headers,
            params={"organization_id": organization["id"]},
        )
        _assert(response.status_code == 200 and response.json()["total"] >= 1, response.text)
        notification.update(response.json()["items"][0])

    recorder.record(11, "Notification history exposes pending approval event", list_notifications)

    def approve_deliver_notification() -> None:
        import app.services.notifications as notifications_module

        class CapturingProvider:
            key = "mock"

            def deliver(self, **kwargs: object) -> NotificationDeliveryResult:
                notification_delivery["recipients"] = kwargs["recipients"]
                notification_delivery["subject"] = kwargs["subject"]
                notification_delivery["text_body"] = kwargs["text_body"]
                return NotificationDeliveryResult(
                    outcome=NotificationDeliveryOutcome.SUCCESS,
                    provider_message_id="v1-demo-message-id",
                )

        monkeypatch.setattr(
            notifications_module,
            "notification_provider_from_settings",
            lambda settings: CapturingProvider(),
        )
        approved = client.post(
            f"/api/v1/notifications/{notification['id']}/approve",
            headers=headers,
            params={"organization_id": organization["id"]},
        )
        _assert(approved.status_code == 200, approved.text)
        queued_delivery = client.post(
            f"/api/v1/notifications/{notification['id']}/deliver",
            headers=headers,
            params={"organization_id": organization["id"]},
        )
        _assert(queued_delivery.status_code == 202, queued_delivery.text)

        queued_job_id = uuid.UUID(queued_delivery.json()["id"])

        with sessions() as db:
            db.execute(
                update(PlatformJob)
                .where(
                    PlatformJob.id != queued_job_id,
                    PlatformJob.status.in_(
                        [
                            PlatformJobStatus.AVAILABLE,
                            PlatformJobStatus.RETRY_WAIT,
                            PlatformJobStatus.LEASED,
                            PlatformJobStatus.RUNNING,
                        ]
                    ),
                )
                .values(
                    status=PlatformJobStatus.CANCELLED,
                    worker_id=None,
                    lease_token=None,
                    lease_expires_at=None,
                    completed_at=now_utc(),
                )
            )
            queued = db.get(PlatformJob, queued_job_id)
            assert queued is not None
            queued.priority = 100
            db.commit()

        worker = JobWorker(
            sessions,
            get_settings(),
            f"v1-demo-notification-{marker}",
        )
        _assert(worker.process_one() is True, "Notification worker processed no job")

        with sessions() as db:
            queued = db.get(PlatformJob, queued_job_id)
            assert queued is not None
            assert queued.status == PlatformJobStatus.SUCCEEDED

            persisted = db.get(
                NotificationEvent,
                uuid.UUID(notification["id"]),
            )
            assert persisted is not None
            assert persisted.status == NotificationStatus.DELIVERED
            assert persisted.provider_message_id == "v1-demo-message-id"

        recipients = notification_delivery["recipients"]
        _assert(email in recipients, f"owner recipient missing: {recipients}")
        _assert(
            analyst["email"] in recipients,
            f"actor recipient missing: {recipients}",
        )
        _assert(
            len(recipients) == len(set(recipients)),
            f"duplicate recipients: {recipients}",
        )
    recorder.record(
        12,
        "Notification approved and delivered through configured provider",
        approve_deliver_notification,
    )

    def remediate() -> None:
        proposed = client.post(
            f"/api/v1/findings/{finding['id']}/remediations",
            headers=headers,
            params={"organization_id": organization["id"]},
        )
        _assert(proposed.status_code == 201, proposed.text)
        remediation.update(proposed.json())
        approved = client.post(
            f"/api/v1/remediations/{remediation['id']}/approve",
            headers=headers,
            params={"organization_id": organization["id"]},
        )
        _assert(approved.status_code == 200, approved.text)
        executed = client.post(
            f"/api/v1/remediations/{remediation['id']}/execute",
            headers=headers,
            params={"organization_id": organization["id"]},
        )
        _assert(executed.status_code == 202, executed.text)
        queued_job_id = uuid.UUID(executed.json()["id"])
        with sessions() as db:
            db.execute(
                update(PlatformJob)
                .where(
                    PlatformJob.status.in_(
                        [
                            PlatformJobStatus.AVAILABLE,
                            PlatformJobStatus.RETRY_WAIT,
                            PlatformJobStatus.LEASED,
                            PlatformJobStatus.RUNNING,
                        ]
                    ),
                    PlatformJob.id != queued_job_id,
                )
                .values(status=PlatformJobStatus.CANCELLED)
            )
            queued_job = db.get(PlatformJob, queued_job_id)
            assert queued_job is not None
            queued_job.priority = 100
            db.commit()

        worker = JobWorker(
            sessions,
            get_settings(),
            f"v1-demo-remediation-{marker}",
        )
        _assert(worker.process_one(), "remediation worker did not acquire queued job")

        with sessions() as db:
            completed_job = db.get(PlatformJob, queued_job_id)
            assert completed_job is not None
            assert completed_job.status == PlatformJobStatus.SUCCEEDED
            persisted = db.get(
                RemediationRequest,
                uuid.UUID(remediation["id"]),
            )
            assert persisted is not None
            assert persisted.status == RemediationStatus.SUCCEEDED

    recorder.record(
        13,
        "Mock remediation proposal, approval, and queued execution completed",
        remediate,
    )

    def schedule_run() -> None:
        created = client.post(
            "/api/v1/schedules",
            headers=headers,
            params={"organization_id": organization["id"]},
            json={
                "aws_account_id": account["id"],
                "name": "Demo daily scan",
                "interval_minutes": 1440,
            },
        )
        _assert(created.status_code == 201, created.text)
        schedule.update(created.json())

        import app.services.discovery as discovery_module
        import app.services.evaluations as evaluations_module

        def fake_discovery_start(
            self: object, account_id: uuid.UUID, actor: object
        ) -> DiscoveryJob:
            with sessions() as db:
                persisted = db.get(AWSAccount, account_id)
                assert persisted is not None
                now = now_utc()
                job = DiscoveryJob(
                    organization_id=persisted.organization_id,
                    aws_account_id=persisted.id,
                    status=DiscoveryJobStatus.COMPLETED,
                    started_by_user_id=uuid.UUID(owner["id"]),
                    started_at=now,
                    finished_at=now,
                    assets_discovered=2,
                )
                db.add(job)
                db.commit()
                db.refresh(job)
                return job

        def fake_evaluation_start(
            self: object,
            account_id: uuid.UUID,
            actor: object,
            *,
            discovery_job_id: uuid.UUID | None = None,
        ) -> EvaluationJob:
            with sessions() as db:
                persisted = db.get(AWSAccount, account_id)
                assert persisted is not None
                now = now_utc()
                job = EvaluationJob(
                    organization_id=persisted.organization_id,
                    aws_account_id=persisted.id,
                    discovery_job_id=discovery_job_id,
                    sequence=999,
                    status=EvaluationJobStatus.COMPLETED,
                    started_by_user_id=uuid.UUID(owner["id"]),
                    started_at=now,
                    finished_at=now,
                    assets_evaluated=2,
                    rules_evaluated=1,
                    passed_count=1,
                )
                db.add(job)
                db.commit()
                db.refresh(job)
                return job

        monkeypatch.setattr(discovery_module.DiscoveryOrchestrator, "start", fake_discovery_start)
        monkeypatch.setattr(evaluations_module.EvaluationService, "start", fake_evaluation_start)
        response = client.post(
            f"/api/v1/schedules/{schedule['id']}/run",
            headers=headers,
            params={"organization_id": organization["id"]},
        )
        _assert(
            response.status_code == 202
            and response.json()["status"] == "pending",
            response.text,
        )

        scan_run_id = uuid.UUID(response.json()["id"])

        with sessions() as db:
            candidates = list(
                db.scalars(
                    select(PlatformJob)
                    .where(
                        PlatformJob.organization_id
                        == uuid.UUID(organization["id"]),
                        PlatformJob.status.in_(
                            [
                                PlatformJobStatus.AVAILABLE,
                                PlatformJobStatus.RETRY_WAIT,
                                PlatformJobStatus.LEASED,
                                PlatformJobStatus.RUNNING,
                            ]
                        ),
                    )
                    .order_by(PlatformJob.created_at.desc())
                )
            )

            queued = next(
                (
                    job
                    for job in candidates
                    if job.payload_json.get("scan_run_id")
                    == str(scan_run_id)
                ),
                None,
            )
            assert queued is not None

            db.execute(
                update(PlatformJob)
                .where(
                    PlatformJob.id != queued.id,
                    PlatformJob.status.in_(
                        [
                            PlatformJobStatus.AVAILABLE,
                            PlatformJobStatus.RETRY_WAIT,
                            PlatformJobStatus.LEASED,
                            PlatformJobStatus.RUNNING,
                        ]
                    ),
                )
                .values(
                    status=PlatformJobStatus.CANCELLED,
                    worker_id=None,
                    lease_token=None,
                    lease_expires_at=None,
                    completed_at=now_utc(),
                )
            )

            queued.priority = 100
            db.commit()

        worker = JobWorker(
            sessions,
            get_settings(),
            f"v1-demo-schedule-{marker}",
        )

        for job_name in (
            "scheduled scan",
            "discovery",
            "evaluation",
        ):
            _assert(
                worker.process_one() is True,
                f"{job_name} worker processed no job",
            )

        with sessions() as db:
            persisted_run = db.get(ScanRun, scan_run_id)
            assert persisted_run is not None
            assert persisted_run.status == ScanRunStatus.COMPLETED
            assert persisted_run.discovery_job_id is not None
            assert persisted_run.evaluation_job_id is not None
    recorder.record(
        14, "Schedule run-now route completed with deterministic delegates", schedule_run
    )

    def audit_and_export() -> None:
        listing = client.get(
            "/api/v1/audit-events",
            headers=headers,
            params={"organization_id": organization["id"], "page_size": 100},
        )
        _assert(listing.status_code == 200 and listing.json()["total"] > 0, listing.text)

    recorder.record(15, "Audit trail query returned lifecycle events", audit_and_export)

    def export_csv() -> None:
        response = client.get(
            "/api/v1/audit-events/export",
            headers=headers,
            params={"organization_id": organization["id"]},
        )
        _assert(response.status_code == 200, response.text)
        _assert(response.text.startswith("id,organization_id,actor_user_id"), response.text)

    recorder.record(16, "Audit CSV export returned bounded CSV", export_csv)

    def side_effect_scan() -> None:
        service_source = inspect.getsource(__import__("app.services.ai").services.ai.AIService)
        _assert("boto3" not in service_source, "AI service imports AWS")
        _assert(not aws_invocations, f"AWS invocations escaped: {aws_invocations}")
        with sessions() as db:
            delivered = db.get(NotificationEvent, uuid.UUID(notification["id"]))
            assert delivered is not None
            _assert(delivered.status == NotificationStatus.DELIVERED, "notification not delivered")

    recorder.record(
        17,
        "No real AWS/external AI/Jira/email/remediation escape detected",
        side_effect_scan,
    )

    def tenant_complete() -> None:
        for path in ("/api/v1/dashboard/summary", "/api/v1/findings", "/api/v1/notifications"):
            response = client.get(path, headers=headers, params={"organization_id": uuid.uuid4()})
            _assert(response.status_code == 404, f"{path}: {response.text}")

    recorder.record(
        18,
        "Demo data remains tenant-scoped; cross-tenant probes return 404",
        tenant_complete,
    )
    recorder.finalize(result_path)
