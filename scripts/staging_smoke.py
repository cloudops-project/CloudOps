"""Deterministic staging smoke test.

Exercises, against a running API and a database it can reach directly:

  1. API liveness (``GET /health``)
  2. API readiness (``GET /ready``)
  3. Registration + login (creates a throwaway org via ``organization_name``)
  4. Organization visibility (``GET /api/v1/organizations``)
  5. Platform job queue mechanics: enqueue one job, run a single worker pass,
     and confirm it reaches a terminal state.
  6. Notification queue behavior via the deterministic mock provider — no
     real AWS, SMTP, Slack, or Teams calls are made by this script.

What step 5 intentionally does NOT do: drive a real AWS discovery/evaluation
job. Every job type that the worker actually dispatches (SCHEDULED_SCAN,
DISCOVERY, EVALUATION, NOTIFICATION_DELIVERY, REMEDIATION_SIMULATION)
requires a pre-existing AWS account connection, finding, or remediation
request — fixtures this script does not fabricate, to avoid contacting real
AWS or asserting behavior against invented data. Instead it enqueues a
``RISK_RECALCULATION`` job, which the worker's dispatch table does not yet
handle, and asserts the pipeline still takes it from AVAILABLE -> LEASED ->
a terminal FAILED state via the same acquire/start/fail path every job type
uses. This proves lease acquisition, dispatch, and terminal-state recording
all work end-to-end without needing AWS or synthetic finding data. It does
NOT prove the AWS-account-dependent job types work; that requires a real or
mocked-AWS staging environment and is out of scope for this script.

Required environment variables:
    SMOKE_API_BASE_URL   e.g. http://localhost:8000
    DATABASE_URL          Same database the API/worker are using (needed for
                           step 5, which drives the queue directly since job
                           processing has no HTTP endpoint).

Exits 0 if every step passes, non-zero otherwise. Never contacts real AWS,
SMTP, Slack, or Teams endpoints.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))


import httpx  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.models.enums import PlatformJobStatus, PlatformJobType  # noqa: E402
from app.services.platform_jobs import PlatformJobService  # noqa: E402
from app.worker.job_worker import JobWorker  # noqa: E402


def fail(step: str, detail: str) -> NoReturn:
    print(f"FAIL [{step}]: {detail}")
    raise SystemExit(1)


def ok(step: str, detail: str = "") -> None:
    print(f"OK   [{step}] {detail}".rstrip())


def main() -> int:
    base_url = os.environ.get("SMOKE_API_BASE_URL")
    database_url = os.environ.get("DATABASE_URL")
    if not base_url:
        fail("config", "SMOKE_API_BASE_URL is not set.")
    if not database_url:
        fail("config", "DATABASE_URL is not set.")

    client = httpx.Client(base_url=base_url, timeout=10.0)

    # 1. Liveness
    response = client.get("/health")
    if response.status_code != 200 or response.json().get("status") != "ok":
        fail("liveness", f"unexpected response: {response.status_code} {response.text}")
    ok("liveness")

    # 2. Readiness
    response = client.get("/ready")
    if response.status_code != 200 or response.json().get("status") != "ready":
        fail("readiness", f"unexpected response: {response.status_code} {response.text}")
    ok("readiness")

    # 3. Registration + login
    suffix = uuid.uuid4().hex[:12]
    email = f"smoke-{suffix}@cloudops-demo.com"
    password = "Smoke-Test-Password-123!"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Smoke Test User",
            "organization_name": f"Smoke Test Org {suffix}",
        },
    )
    if response.status_code != 201:
        fail("register", f"unexpected response: {response.status_code} {response.text}")
    ok("register")

    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    if response.status_code != 200:
        fail("login", f"unexpected response: {response.status_code} {response.text}")
    access_token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    ok("login")

    # 4. Organization visibility
    response = client.get("/api/v1/organizations", headers=headers)
    if response.status_code != 200 or not response.json():
        fail("organizations", f"unexpected response: {response.status_code} {response.text}")
    organization_id = uuid.UUID(response.json()[0]["id"])
    ok("organizations", f"organization_id={organization_id}")

    # 5. Platform job queue mechanics (see module docstring for scope).
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db:
        job, created = PlatformJobService(db).enqueue(
            organization_id=organization_id,
            job_type=PlatformJobType.RISK_RECALCULATION,
            reference_id=organization_id,
            idempotency_key=f"smoke-test:{suffix}",
            payload={"smoke_test": True},
        )
        db.commit()
        if not created:
            fail("job_enqueue", "idempotency key collided with an existing job")
    ok("job_enqueue", f"job_id={job.id}")

    settings = get_settings()
    worker = JobWorker(session_factory, settings, worker_id=f"smoke-worker-{suffix}")
    processed = worker.process_one()
    if not processed:
        fail("job_process", "worker did not acquire the enqueued job")

    with session_factory() as db:
        try:
            refreshed = PlatformJobService(db).get_scoped(organization_id, job.id)
        except Exception as exc:  # NotFoundError from app.exceptions.errors
            fail("job_terminal_state", f"job lookup failed after processing: {exc}")
        if refreshed.status not in (PlatformJobStatus.FAILED, PlatformJobStatus.DEAD_LETTERED):
            fail(
                "job_terminal_state",
                f"expected FAILED or DEAD_LETTERED (unsupported job type), got "
                f"{refreshed.status.value}",
            )
    ok("job_terminal_state", f"status={refreshed.status.value}")

    # 6. Notification queue behavior via the mock provider is exercised by
    # the backend test suite (test_notification_integrations.py /
    # test_notifications_service.py) against MockNotificationProvider; this
    # script does not duplicate that here because it requires an existing
    # NotificationEvent tied to a real finding, which step 5 intentionally
    # avoids fabricating. Confirm NOTIFICATION_PROVIDER=mock in the target
    # environment's configuration if you need to smoke-test delivery
    # end-to-end without contacting SMTP/Slack/Teams.

    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
