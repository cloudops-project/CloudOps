from __future__ import annotations

import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session, sessionmaker

from app.models import AIPromptTemplate, AIRequest, AIRequestSource, AIResponse
from app.models.enums import AIRequestStatus, AISourceType, AITaskType
from app.schemas.ai import AIGenerateRequest, AISourceInput
from app.services.ai import AIService
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
        )
        db.add(request)
        db.flush()
        db.add(
            AIRequestSource(
                request_id=request.id,
                organization_id=org_b.id,
                source_type=AISourceType.FINDING,
                source_id=org_b.id,
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

    def worker() -> str:
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            try:
                result = AIService(db).generate(
                    AIGenerateRequest(
                        organization_id=organization_id,
                        task_type=AITaskType.EXPLAIN_FINDING,
                        sources=[
                            AISourceInput(source_type=AISourceType.FINDING, source_id=finding_id)
                        ],
                        idempotency_key="concurrent-idempotency",
                    ),
                    user_id,
                )
                return str(result.id)
            except Exception:
                db.rollback()
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert results.count("conflict") <= 1
    with pg_sessions() as db:
        rows = db.scalars(
            select(AIRequest).where(
                AIRequest.organization_id == organization_id,
                AIRequest.idempotency_key == "concurrent-idempotency",
            )
        ).all()
        assert len(rows) == 1
