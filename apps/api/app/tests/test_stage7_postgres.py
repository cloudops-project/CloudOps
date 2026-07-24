from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session, sessionmaker

from app.exceptions.errors import AppError
from app.models import (
    AIPromptTemplate,
    AIRequest,
    AIRequestSource,
    AIResponse,
    AIUsageWindow,
)
from app.models.enums import AIRequestStatus, AISourceType, AITaskType
from app.schemas.ai import AIGenerateRequest, AISourceInput
from app.services.ai import AIService
from app.services.ai_provider import MockAIProvider
from app.tests.test_risk import _finding, _tenant

POSTGRES_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
database_name = make_url(POSTGRES_URL).database if POSTGRES_URL else ""
if POSTGRES_URL and not (
    database_name == "cloudops_test" or str(database_name).startswith("cloudops_e2e_")
):
    raise RuntimeError("Stage 7 PostgreSQL tests require a disposable CloudOps test database.")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="POSTGRES_TEST_DATABASE_URL is required for Stage 7 integrity tests",
)


@pytest.fixture(scope="module")
def pg_sessions() -> Generator[sessionmaker[Session], None, None]:
    assert POSTGRES_URL is not None
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def test_ai_source_and_response_snapshots_are_database_immutable(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        user, organization, account = _tenant(db)
        finding, _ = _finding(db, organization, account, user)
        db.commit()
        result = AIService(db).generate(
            AIGenerateRequest(
                organization_id=organization.id,
                task_type=AITaskType.EXPLAIN_FINDING,
                sources=[AISourceInput(source_type=AISourceType.FINDING, source_id=finding.id)],
                idempotency_key="postgres-immutability",
            ),
            user.id,
        )
        source = db.scalar(select(AIRequestSource).where(AIRequestSource.request_id == result.id))
        response = db.scalar(select(AIResponse).where(AIResponse.request_id == result.id))
        assert source is not None and response is not None
        source.source_version += 1
        with pytest.raises(DatabaseError, match="immutable"):
            db.commit()
        db.rollback()
        response.content_json = {"title": "tampered"}
        with pytest.raises(DatabaseError, match="immutable"):
            db.commit()
        db.rollback()


def test_exactly_one_typed_source_is_database_enforced(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        user, organization, account = _tenant(db)
        finding, _ = _finding(db, organization, account, user)
        db.commit()
        result = AIService(db).generate(
            AIGenerateRequest(
                organization_id=organization.id,
                task_type=AITaskType.EXPLAIN_FINDING,
                sources=[AISourceInput(source_type=AISourceType.FINDING, source_id=finding.id)],
                idempotency_key="exactly-one-source",
            ),
            user.id,
        )
        source = db.scalar(select(AIRequestSource).where(AIRequestSource.request_id == result.id))
        assert source is not None
        db.add(
            AIRequestSource(
                request_id=result.id,
                organization_id=organization.id,
                source_type=AISourceType.FINDING,
                source_id=finding.id,
                finding_id=finding.id,
                finding_aws_account_id=finding.aws_account_id,
                source_version=finding.lifecycle_version,
                source_hash="a" * 64,
            )
        )
        with pytest.raises(DatabaseError):
            db.commit()
        db.rollback()


def test_ai_request_source_composite_tenant_constraint(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        user_a, org_a, _ = _tenant(db)
        _, org_b, _ = _tenant(db)
        template = db.scalar(
            select(AIPromptTemplate).where(AIPromptTemplate.task_type == AITaskType.EXPLAIN_FINDING)
        )
        assert template is not None
        request = AIRequest(
            organization_id=org_a.id,
            requested_by_user_id=user_a.id,
            task_type=AITaskType.EXPLAIN_FINDING,
            status=AIRequestStatus.RUNNING,
            idempotency_key="cross-tenant-postgres",
            provider_key="mock",
            prompt_key=template.key,
            prompt_version=template.version,
            context_hash="a" * 64,
            request_fingerprint="c" * 64,
            response_schema_version=template.schema_version,
            model_key="mock",
        )
        db.add(request)
        db.flush()
        db.add(
            AIRequestSource(
                request_id=request.id,
                organization_id=org_b.id,
                source_type=AISourceType.FINDING,
                source_id=org_b.id,
                finding_id=org_b.id,
                finding_aws_account_id=org_b.id,
                source_version=1,
                source_hash="b" * 64,
            )
        )
        with pytest.raises(DatabaseError):
            db.commit()
        db.rollback()


def test_concurrent_duplicate_idempotency_has_one_winner(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as seed:
        user, organization, account = _tenant(seed)
        finding, _ = _finding(seed, organization, account, user)
        seed.commit()
        user_id, organization_id, finding_id = user.id, organization.id, finding.id
    barrier = Barrier(2)
    provider = MockAIProvider()

    def worker() -> str:
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            result = AIService(db, provider).generate(
                AIGenerateRequest(
                    organization_id=organization_id,
                    task_type=AITaskType.EXPLAIN_FINDING,
                    sources=[AISourceInput(source_type=AISourceType.FINDING, source_id=finding_id)],
                    idempotency_key="concurrent-idempotency",
                ),
                user_id,
            )
            return str(result.id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert len(set(results)) == 1
    assert provider.invocations == 1
    with pg_sessions() as db:
        rows = db.scalars(
            select(AIRequest).where(
                AIRequest.organization_id == organization_id,
                AIRequest.idempotency_key == "concurrent-idempotency",
            )
        ).all()
        assert len(rows) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AIRequestSource)
                .where(AIRequestSource.request_id == rows[0].id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AIResponse)
                .where(AIResponse.request_id == rows[0].id)
            )
            == 1
        )
        usage = db.scalar(
            select(AIUsageWindow).where(AIUsageWindow.organization_id == organization_id)
        )
        assert usage is not None and usage.request_count == 1


def test_used_prompt_template_is_database_immutable(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        user, organization, account = _tenant(db)
        finding, _ = _finding(db, organization, account, user)
        db.commit()
        AIService(db).generate(
            AIGenerateRequest(
                organization_id=organization.id,
                task_type=AITaskType.EXPLAIN_FINDING,
                sources=[AISourceInput(source_type=AISourceType.FINDING, source_id=finding.id)],
                idempotency_key="used-template-immutable",
            ),
            user.id,
        )
        template = db.scalar(
            select(AIPromptTemplate).where(AIPromptTemplate.task_type == AITaskType.EXPLAIN_FINDING)
        )
        assert template is not None
        template.system_instructions = "tampered"
        with pytest.raises(DatabaseError, match="immutable"):
            db.commit()
        db.rollback()
        db.delete(template)
        with pytest.raises(DatabaseError, match="immutable"):
            db.commit()
        db.rollback()


def test_completed_request_requires_response_at_commit(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        user, organization, _ = _tenant(db)
        template = db.scalar(
            select(AIPromptTemplate).where(AIPromptTemplate.task_type == AITaskType.EXPLAIN_FINDING)
        )
        assert template is not None
        db.add(
            AIRequest(
                organization_id=organization.id,
                requested_by_user_id=user.id,
                task_type=AITaskType.EXPLAIN_FINDING,
                status=AIRequestStatus.COMPLETED,
                idempotency_key="completed-without-response",
                provider_key="mock",
                model_key="mock",
                prompt_key=template.key,
                prompt_version=template.version,
                response_schema_version=template.schema_version,
                context_hash="a" * 64,
                request_fingerprint="b" * 64,
                finished_at=datetime.now(UTC),
            )
        )
        with pytest.raises(DatabaseError, match="requires exactly one response"):
            db.commit()
        db.rollback()


@pytest.mark.parametrize(
    "terminal_status",
    [
        AIRequestStatus.FAILED,
        AIRequestStatus.TIMED_OUT,
        AIRequestStatus.PROVIDER_DISABLED,
        AIRequestStatus.INVALID_RESPONSE,
        AIRequestStatus.RATE_LIMITED,
    ],
)
def test_failed_request_cannot_retain_successful_response(
    pg_sessions: sessionmaker[Session],
    terminal_status: AIRequestStatus,
) -> None:
    with pg_sessions() as db:
        user, organization, _ = _tenant(db)
        template = db.scalar(
            select(AIPromptTemplate).where(AIPromptTemplate.task_type == AITaskType.EXPLAIN_FINDING)
        )
        assert template is not None
        request = AIRequest(
            organization_id=organization.id,
            requested_by_user_id=user.id,
            task_type=AITaskType.EXPLAIN_FINDING,
            status=terminal_status,
            idempotency_key=f"{terminal_status.value}-cannot-have-response",
            provider_key="mock",
            model_key="mock",
            prompt_key=template.key,
            prompt_version=template.version,
            response_schema_version=template.schema_version,
            context_hash="a" * 64,
            request_fingerprint="b" * 64,
            error_code="AI_PROVIDER_FAILED",
            finished_at=datetime.now(UTC),
        )
        db.add(request)
        db.flush()
        db.add(
            AIResponse(
                request_id=request.id,
                organization_id=organization.id,
                content_json={"title": "must not persist"},
                schema_version=1,
                output_hash="c" * 64,
            )
        )
        with pytest.raises(DatabaseError, match="cannot retain a response"):
            db.commit()
        db.rollback()


@pytest.mark.parametrize("invalid_status", [AIRequestStatus.PENDING, AIRequestStatus.RUNNING])
def test_terminal_request_cannot_return_to_active_state(
    pg_sessions: sessionmaker[Session],
    invalid_status: AIRequestStatus,
) -> None:
    with pg_sessions() as db:
        user, organization, account = _tenant(db)
        finding, _ = _finding(db, organization, account, user)
        db.commit()
        generated = AIService(db).generate(
            AIGenerateRequest(
                organization_id=organization.id,
                task_type=AITaskType.EXPLAIN_FINDING,
                sources=[AISourceInput(source_type=AISourceType.FINDING, source_id=finding.id)],
                idempotency_key=f"terminal-transition-{invalid_status.value}",
            ),
            user.id,
        )
        request = db.get(AIRequest, generated.id)
        assert request is not None
        request.status = invalid_status
        request.finished_at = None
        with pytest.raises(DatabaseError, match="terminal AI request status is immutable"):
            db.commit()
        db.rollback()


def test_concurrent_conflicting_idempotency_has_one_winner_and_one_conflict(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as seed:
        user, organization, account = _tenant(seed)
        finding, _ = _finding(seed, organization, account, user)
        seed.commit()
        user_id, organization_id, finding_id = user.id, organization.id, finding.id
    barrier = Barrier(2)
    tasks = [AITaskType.EXPLAIN_FINDING, AITaskType.EXPLAIN_BUSINESS_IMPACT]

    def worker(task: AITaskType) -> str:
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            try:
                AIService(db).generate(
                    AIGenerateRequest(
                        organization_id=organization_id,
                        task_type=task,
                        sources=[
                            AISourceInput(
                                source_type=AISourceType.FINDING,
                                source_id=finding_id,
                            )
                        ],
                        idempotency_key="concurrent-conflicting-idempotency",
                    ),
                    user_id,
                )
                return "completed"
            except Exception as exc:
                db.rollback()
                return str(getattr(exc, "code", "unexpected"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, tasks))
    assert results.count("completed") == 1
    assert results.count("AI_IDEMPOTENCY_CONFLICT") == 1


def test_concurrent_quota_boundary_has_one_winner(
    pg_sessions: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pg_sessions() as seed:
        user, organization, account = _tenant(seed)
        finding, _ = _finding(seed, organization, account, user)
        seed.commit()
        user_id, organization_id, finding_id = user.id, organization.id, finding.id
    monkeypatch.setattr(AIService, "MAX_REQUESTS_PER_HOUR", 1)
    barrier = Barrier(2)

    def worker(index: int) -> str:
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            try:
                AIService(db).generate(
                    AIGenerateRequest(
                        organization_id=organization_id,
                        task_type=AITaskType.EXPLAIN_FINDING,
                        sources=[
                            AISourceInput(
                                source_type=AISourceType.FINDING,
                                source_id=finding_id,
                            )
                        ],
                        idempotency_key=f"quota-boundary-{index}",
                    ),
                    user_id,
                )
                return "completed"
            except Exception as exc:
                db.rollback()
                return str(getattr(exc, "code", "unexpected"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker, range(2)))
    assert results.count("completed") == 1
    assert results.count("AI_RATE_LIMITED") == 1


def test_quota_is_organization_scoped_and_rolls_over_at_utc_hour(
    pg_sessions: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pg_sessions() as db:
        user_a, organization_a, account_a = _tenant(db)
        finding_a, _ = _finding(db, organization_a, account_a, user_a)
        user_b, organization_b, account_b = _tenant(db)
        finding_b, _ = _finding(db, organization_b, account_b, user_b)
        db.commit()
        now = [datetime(2026, 7, 24, 10, 59, 30, tzinfo=UTC)]
        monkeypatch.setattr(AIService, "MAX_REQUESTS_PER_HOUR", 1)

        def generate(
            organization_id: uuid.UUID,
            finding_id: uuid.UUID,
            user_id: uuid.UUID,
            key: str,
        ) -> object:
            return AIService(db, utc_now=lambda: now[0]).generate(
                AIGenerateRequest(
                    organization_id=organization_id,
                    task_type=AITaskType.EXPLAIN_FINDING,
                    sources=[AISourceInput(source_type=AISourceType.FINDING, source_id=finding_id)],
                    idempotency_key=key,
                ),
                user_id,
            )

        generate(organization_a.id, finding_a.id, user_a.id, "quota-org-a-first")
        with pytest.raises(AppError) as limited:
            generate(organization_a.id, finding_a.id, user_a.id, "quota-org-a-limited")
        assert limited.value.code == "AI_RATE_LIMITED"
        details = limited.value.details[0]
        assert 1 <= details["retry_after_seconds"] <= 30
        generate(organization_b.id, finding_b.id, user_b.id, "quota-org-b-first")

        now[0] = datetime(2026, 7, 24, 11, 0, 5, tzinfo=UTC)
        generate(organization_a.id, finding_a.id, user_a.id, "quota-org-a-next-window")

        windows = db.scalars(
            select(AIUsageWindow)
            .where(AIUsageWindow.organization_id.in_([organization_a.id, organization_b.id]))
            .order_by(AIUsageWindow.organization_id, AIUsageWindow.window_start)
        ).all()
        assert len(windows) == 3
        assert all(window.request_count == 1 for window in windows)
        assert len({window.organization_id for window in windows}) == 2
        assert (
            len(
                {
                    window.window_start
                    for window in windows
                    if window.organization_id == organization_a.id
                }
            )
            == 2
        )


@pytest.mark.parametrize(
    "lock_key",
    [
        "ai-request:00000000-0000-0000-0000-000000000001:lock-release",
        "ai-quota:00000000-0000-0000-0000-000000000001:2026-07-24T10:00:00+00:00",
    ],
)
def test_stage7_transaction_locks_are_reacquirable_after_rollback(
    pg_sessions: sessionmaker[Session], lock_key: str
) -> None:
    first = pg_sessions()
    second = pg_sessions()
    try:
        first.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": lock_key},
        )
        first.rollback()
        acquired = second.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
            {"key": lock_key},
        )
        assert acquired is True
        second.rollback()
    finally:
        first.close()
        second.close()
