"""Regression tests for the two-day local demo path.

These cover the demo defects observed during live setup: the web port mismatch,
the same-origin API proxy, the SecretStr seed failure, the synthetic-inventory
metadata drift that produced repeated `security.evaluation.rule_error` warnings,
and the scheduler/job-worker wiring that "Run now" depends on.

compose.demo.yml is inspected with a small indentation-based block reader rather
than a YAML parser, because PyYAML is not a declared dependency of this package
and the demo fix does not justify adding one.

Nothing here contacts AWS, Bedrock, SES, SMTP, Slack, Teams, or Jira.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.exceptions.errors import ForbiddenError, NotFoundError
from app.models import (
    AuditEvent,
    AWSAccount,
    Finding,
    Organization,
    OrganizationMembership,
    PlatformJob,
    User,
)
from app.models.enums import (
    AWSAccountStatus,
    EvaluationJobStatus,
    FindingSeverity,
    MembershipStatus,
    OrganizationRole,
    PlatformJobType,
    RemediationExecutionMode,
    RemediationStatus,
    ScanRunTrigger,
    UserStatus,
)
from app.security.passwords import hash_password
from app.services.demo_inventory import synthetic_inventory
from app.services.discovery import DiscoveryOrchestrator
from app.services.evaluations import EvaluationService
from app.services.remediation import RemediationService
from app.services.scheduler import SchedulerService

REPO_ROOT = Path(__file__).resolve().parents[4]
COMPOSE_DEMO = REPO_ROOT / "compose.demo.yml"
NGINX_CONF = REPO_ROOT / "apps" / "web" / "nginx.conf"
WEB_DOCKERFILE = REPO_ROOT / "apps" / "web" / "Dockerfile"
DEMO_SEED = REPO_ROOT / "scripts" / "demo_seed.py"

DEMO_ACCOUNT_ID = "123456789012"


def _compose_text() -> str:
    assert COMPOSE_DEMO.exists(), f"compose.demo.yml not found at {COMPOSE_DEMO}"
    return COMPOSE_DEMO.read_text(encoding="utf-8")


def _service_blocks() -> dict[str, str]:
    """Split compose.demo.yml into `service name -> raw block text`."""
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    in_services = False
    for line in _compose_text().splitlines():
        stripped = line.strip()
        if not line.startswith(" ") and stripped:
            in_services = stripped == "services:"
            current = None
            continue
        if not in_services or not stripped:
            continue
        is_service_header = (
            line.startswith("  ")
            and not line.startswith("   ")
            and stripped.endswith(":")
            and not stripped.startswith("#")
        )
        if is_service_header:
            current = stripped[:-1]
            blocks[current] = []
            continue
        if current is not None:
            blocks[current].append(line)
    return {name: "\n".join(body) for name, body in blocks.items()}


# --------------------------------------------------------------------------
# 1-5: demo container and same-origin proxy contract
# --------------------------------------------------------------------------


def test_compose_demo_maps_host_5173_to_container_8080() -> None:
    web = _service_blocks()["web"]
    assert '"5173:8080"' in web, (
        "The web image serves nginx on 8080; mapping 5173:5173 leaves the demo "
        "unreachable."
    )
    assert '"5173:5173"' not in web


def test_demo_web_image_uses_same_origin_api_base_url() -> None:
    web = _service_blocks()["web"]
    assert 'VITE_API_BASE_URL: ""' in web, (
        "The demo bundle must build with an empty base URL so the SPA calls "
        "relative /api/v1 paths and one tunnel serves both origins."
    )
    # A runtime environment value cannot influence an already-built Vite bundle,
    # so its presence in `environment:` would be misleading.
    assert "VITE_API_BASE_URL: http" not in web


def test_web_dockerfile_accepts_empty_api_base_url_build_arg() -> None:
    content = WEB_DOCKERFILE.read_text(encoding="utf-8")
    assert "ARG VITE_API_BASE_URL=" in content
    assert "EXPOSE 8080" in content


def test_nginx_proxies_api_prefix_without_stripping_the_path() -> None:
    content = NGINX_CONF.read_text(encoding="utf-8")
    assert "location /api/" in content
    # A trailing slash on proxy_pass would strip /api and break every route.
    assert "proxy_pass http://api:8000;" in content
    assert "proxy_pass http://api:8000/;" not in content
    for header in (
        "X-Real-IP",
        "X-Forwarded-For",
        "X-Forwarded-Proto",
        "X-Forwarded-Host",
        "X-CloudOps-Demo-Proxy",
    ):
        assert header in content


def test_nginx_keeps_spa_fallback_and_healthz() -> None:
    content = NGINX_CONF.read_text(encoding="utf-8")
    assert "try_files $uri $uri/ /index.html;" in content
    assert "location = /healthz" in content
    assert "location = /api/health" in content
    assert "location = /api/ready" in content


def test_demo_api_is_not_published_directly() -> None:
    api = _service_blocks()["api"]
    assert "ports:" not in api
    assert "8000:8000" not in api


def test_nginx_cache_boundaries_are_explicit() -> None:
    content = NGINX_CONF.read_text(encoding="utf-8")
    api_block = content.split("location /api/", 1)[1].split("location ~*", 1)[0]
    assert 'Cache-Control "no-store"' in api_block
    static_block = content.split("location ~*", 1)[1].split(
        "location = /index.html", 1
    )[0]
    assert 'Cache-Control "public, immutable"' in static_block


def test_nginx_adds_no_wildcard_host_or_cors_origin() -> None:
    content = NGINX_CONF.read_text(encoding="utf-8")
    assert "Access-Control-Allow-Origin" not in content
    assert 'Host "*"' not in content


# --------------------------------------------------------------------------
# 6-9: seed guardrails
# --------------------------------------------------------------------------


def test_demo_seed_unwraps_secretstr_via_database_dsn() -> None:
    content = DEMO_SEED.read_text(encoding="utf-8")
    assert "make_url(settings.database_dsn)" in content, (
        "make_url(settings.database_url) fails with "
        "'Expected string or URL object, got SecretStr'."
    )
    assert "make_url(settings.database_url)" not in content


def test_database_dsn_reveals_secret_for_sqlalchemy() -> None:
    settings = Settings(
        app_env="development",
        database_url=SecretStr(
            "postgresql+psycopg://cloudops:demo@localhost:5432/cloudops_demo"
        ),
        jwt_secret_key=SecretStr("demo-only-jwt-secret-at-least-32-characters"),
    )
    assert isinstance(settings.database_dsn, str)
    assert "SecretStr" not in settings.database_dsn
    assert "cloudops_demo" in settings.database_dsn


def test_demo_seed_refuses_production_and_non_demo_databases() -> None:
    content = DEMO_SEED.read_text(encoding="utf-8")
    assert 'if settings.app_env in {"staging", "production"}' in content
    assert 'database_name != "cloudops_demo"' in content
    assert 'startswith("cloudops_demo_")' in content


def test_demo_seed_offers_a_safe_reset_instead_of_partial_reseed() -> None:
    content = DEMO_SEED.read_text(encoding="utf-8")
    assert "_existing_demo_organization_slug()" in content
    assert "--reset" in content


# --------------------------------------------------------------------------
# Fixtures for the database-backed demo tests
# --------------------------------------------------------------------------


def _demo_org(db: Session) -> tuple[User, Organization, AWSAccount]:
    owner = User(
        email="owner@cloudops-demo.testmail.com",
        normalized_email="owner@cloudops-demo.testmail.com",
        password_hash=hash_password("CloudOps-Demo-Password-123!"),
        full_name="CloudOps Demo Owner",
        status=UserStatus.ACTIVE,
    )
    db.add(owner)
    db.flush()
    organization = Organization(
        name="CloudOps Demo", slug="cloudops-demo", created_by_user_id=owner.id
    )
    db.add(organization)
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=owner.id,
            role=OrganizationRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
    )
    account = AWSAccount(
        organization_id=organization.id,
        name="Demo AWS Account",
        account_id=DEMO_ACCOUNT_ID,
        role_arn=f"arn:aws:iam::{DEMO_ACCOUNT_ID}:role/CloudOpsReadOnlyRole",
        external_id="cloudops-demo-external-id",
        status=AWSAccountStatus.CONNECTED,
        connection_status=AWSAccountStatus.CONNECTED,
        created_by_user_id=owner.id,
    )
    db.add(account)
    db.flush()
    db.commit()
    return owner, organization, account


def _demo_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "development",
        "database_url": SecretStr("sqlite+pysqlite:///:memory:"),
        "jwt_secret_key": SecretStr("demo-only-jwt-secret-at-least-32-characters"),
        "demo_synthetic_discovery": True,
        "remediation_execution_enabled": True,
    }
    values.update(overrides)
    return Settings(**values)


# --------------------------------------------------------------------------
# 10-12: synthetic inventory produces deterministic findings, no rule errors
# --------------------------------------------------------------------------


def test_synthetic_discovery_creates_seeded_assets_without_aws(db: Session) -> None:
    owner, _organization, account = _demo_org(db)
    job = DiscoveryOrchestrator(db, _demo_settings()).start(account.id, owner)
    assert job.assets_created == len(synthetic_inventory(DEMO_ACCOUNT_ID))
    assert job.assets_discovered == job.assets_created


def test_synthetic_inventory_evaluates_without_rule_errors(db: Session) -> None:
    owner, _organization, account = _demo_org(db)
    DiscoveryOrchestrator(db, _demo_settings()).start(account.id, owner)
    evaluation = EvaluationService(db).start(account.id, owner)
    assert evaluation.evaluation_errors == 0, (
        "A rule returned invalid_or_incomplete_metadata: synthetic asset metadata "
        "keys have drifted from the rule contract in app/services/demo_inventory.py."
    )
    assert evaluation.status == EvaluationJobStatus.COMPLETED


def test_expected_critical_and_high_demo_findings_exist(db: Session) -> None:
    owner, organization, account = _demo_org(db)
    DiscoveryOrchestrator(db, _demo_settings()).start(account.id, owner)
    EvaluationService(db).start(account.id, owner)

    findings = list(
        db.scalars(select(Finding).where(Finding.organization_id == organization.id))
    )
    severities = {finding.rule_key: finding.severity for finding in findings}

    # The two headline demo findings that never appeared before this fix, because
    # the seed wrote metadata keys the rules do not read.
    assert severities.get("EC2_SG_SSH_OPEN_TO_WORLD") == FindingSeverity.CRITICAL
    assert severities.get("S3_BUCKET_PUBLIC_ACCESS_CONFIRMED") == FindingSeverity.CRITICAL

    assert "IAM_USER_CONSOLE_ACCESS_WITHOUT_MFA" in severities
    assert "CLOUDTRAIL_LOGGING_DISABLED" in severities
    assert severities.get("EC2_INSTANCE_IMDSV1_ALLOWED") == FindingSeverity.HIGH

    # Rules that correctly find nothing must not fabricate findings.
    assert "EC2_SG_RDP_OPEN_TO_WORLD" not in severities
    assert "CLOUDTRAIL_DELIVERY_FAILURE" not in severities


def test_synthetic_discovery_is_refused_in_production_like_environments() -> None:
    with pytest.raises(ValueError, match="DEMO_SYNTHETIC_DISCOVERY"):
        Settings(
            app_env="production",
            database_url=SecretStr("postgresql+psycopg://cloudops:pw@db.invalid/cloudops"),
            jwt_secret_key=SecretStr("production-key-with-at-least-32-characters"),
            cookie_secure=True,
            cors_allowed_origins="https://cloudops.example.invalid",
            demo_synthetic_discovery=True,
        )


def test_real_discovery_path_is_unchanged_when_flag_is_off(db: Session) -> None:
    orchestrator = DiscoveryOrchestrator(db, _demo_settings(demo_synthetic_discovery=False))
    # Falls back to the real collectors and the STS factory, so production
    # discovery behaviour is untouched by the demo flag.
    assert orchestrator.client_factory is None
    assert orchestrator.services is DiscoveryOrchestrator.services


# --------------------------------------------------------------------------
# 13-16: schedule, run-now and worker processing
# --------------------------------------------------------------------------


def test_demo_schedule_can_be_created_and_run_now_enqueues_a_job(db: Session) -> None:
    owner, organization, account = _demo_org(db)
    scheduler = SchedulerService(db, _demo_settings())
    schedule = scheduler.create_schedule(
        organization.id, account.id, owner, name="Daily demo scan", interval_minutes=1440
    )
    assert schedule.id is not None

    run = scheduler.run_schedule(
        organization.id, schedule.id, owner, trigger=ScanRunTrigger.MANUAL
    )
    assert run.aws_account_id == account.id

    job = db.scalar(
        select(PlatformJob).where(PlatformJob.organization_id == organization.id)
    )
    assert job is not None, "Run now must enqueue a job; it never scans inline."
    assert job.job_type == PlatformJobType.SCHEDULED_SCAN


def test_compose_demo_runs_scheduler_and_job_workers_by_default() -> None:
    blocks = _service_blocks()
    for name in ("scheduler-worker", "job-worker"):
        assert name in blocks, f"{name} must exist in compose.demo.yml"
        assert "profiles:" not in blocks[name], (
            f"{name} must not sit behind a manual profile; Run now would never "
            "leave PENDING."
        )
        assert 'os.kill(1, 0)' in blocks[name], (
            f"{name} must override the API image's HTTP healthcheck with a "
            "worker-process liveness check."
        )
    assert "app.worker.job_worker" in blocks["job-worker"]
    assert "app.worker.scheduler_worker" in blocks["scheduler-worker"]


def test_scheduled_run_preserves_tenant_boundaries(db: Session) -> None:
    owner, organization, account = _demo_org(db)
    scheduler = SchedulerService(db, _demo_settings())
    schedule = scheduler.create_schedule(
        organization.id, account.id, owner, name="Daily demo scan", interval_minutes=1440
    )
    with pytest.raises((NotFoundError, ForbiddenError)):
        scheduler.run_schedule(
            uuid.uuid4(), schedule.id, owner, trigger=ScanRunTrigger.MANUAL
        )


# --------------------------------------------------------------------------
# 17-19: dry-run remediation and audit evidence
# --------------------------------------------------------------------------


def test_demo_remediation_is_proposed_dry_run_and_never_auto_approved(db: Session) -> None:
    owner, organization, account = _demo_org(db)
    DiscoveryOrchestrator(db, _demo_settings()).start(account.id, owner)
    EvaluationService(db).start(account.id, owner)

    finding = db.scalar(
        select(Finding).where(
            Finding.organization_id == organization.id,
            Finding.rule_key == "EC2_SG_SSH_OPEN_TO_WORLD",
        )
    )
    assert finding is not None
    request = RemediationService(db).propose_for_finding(organization.id, finding.id, owner)

    assert request.dry_run is True
    assert request.execution_mode == RemediationExecutionMode.MOCK_AUTOMATION
    assert request.status == RemediationStatus.PENDING_APPROVAL


def test_demo_remediation_tenant_scope_is_enforced(db: Session) -> None:
    owner, organization, account = _demo_org(db)
    DiscoveryOrchestrator(db, _demo_settings()).start(account.id, owner)
    EvaluationService(db).start(account.id, owner)
    finding = db.scalar(
        select(Finding).where(Finding.organization_id == organization.id)
    )
    assert finding is not None

    outsider = User(
        email="outsider@example.invalid",
        normalized_email="outsider@example.invalid",
        password_hash=hash_password("Strong-Password-123!"),
        full_name="Outsider",
        status=UserStatus.ACTIVE,
    )
    db.add(outsider)
    db.flush()
    db.commit()

    with pytest.raises(NotFoundError):
        RemediationService(db).propose_for_finding(uuid.uuid4(), finding.id, outsider)


def test_demo_remediation_never_enables_live_aws() -> None:
    for name in ("api", "job-worker"):
        block = _service_blocks()[name]
        assert "REMEDIATION_LIVE_AWS_ENABLED" not in block or (
            'REMEDIATION_LIVE_AWS_ENABLED: "true"' not in block
        )


def test_demo_audit_events_are_recorded_for_discovery(db: Session) -> None:
    owner, organization, account = _demo_org(db)
    DiscoveryOrchestrator(db, _demo_settings()).start(account.id, owner)

    events = list(
        db.scalars(select(AuditEvent).where(AuditEvent.organization_id == organization.id))
    )
    assert any(event.event_type == "aws.discovery.started" for event in events)


# --------------------------------------------------------------------------
# 20-24: the demo requires no paid, live, or production provider
# --------------------------------------------------------------------------


def test_demo_requires_no_live_bedrock_ses_or_jira() -> None:
    for name, block in _service_blocks().items():
        if name in {"postgres", "mailpit", "web", "cloudflared"}:
            continue
        assert "AI_PROVIDER: mock" in block, f"{name} must use the mock AI provider"
        assert 'AWS_BEDROCK_ENABLED: "true"' not in block
        assert 'AWS_SES_ENABLED: "true"' not in block
        assert "NOTIFICATION_PROVIDER: ses" not in block
        assert "JIRA" not in block


def test_demo_stack_introduces_no_production_setting() -> None:
    text = _compose_text()
    assert "APP_ENV: production" not in text
    assert "APP_ENV: staging" not in text
    assert 'HSTS_ENABLED: "true"' not in text
    for name, block in _service_blocks().items():
        if "APP_ENV:" in block:
            assert "APP_ENV: development" in block, (
                f"{name} must stay on APP_ENV=development for the local demo"
            )


def test_demo_stack_declares_no_wildcard_cors_or_trusted_host() -> None:
    for line in _compose_text().splitlines():
        if "CORS_ALLOWED_ORIGINS:" in line or "TRUSTED_HOSTS:" in line:
            assert "*" not in line, f"Wildcard in demo configuration: {line.strip()}"


def test_demo_login_works_through_the_same_origin_api_path(client: Any) -> None:
    """The SPA posts to a relative /api/v1 path; that exact path must authenticate."""
    payload = {
        "email": "owner@cloudops-demo.testmail.com",
        "password": "CloudOps-Demo-Password-123!",
        "full_name": "CloudOps Demo Owner",
        "organization_name": "CloudOps Demo",
    }
    registered = client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201, registered.text

    response = client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]
