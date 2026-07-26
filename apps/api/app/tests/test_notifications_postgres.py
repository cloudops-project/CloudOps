from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import get_settings
from app.models import NotificationEvent, User
from app.models.enums import NotificationChannel, NotificationStatus
from app.tests.test_risk import _finding, _tenant

POSTGRES_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
database_name = make_url(POSTGRES_URL).database if POSTGRES_URL else ""
if POSTGRES_URL and not (
    database_name == "cloudops_test" or str(database_name).startswith("cloudops_e2e_")
):
    raise RuntimeError("Stage 9 PostgreSQL tests require a disposable CloudOps test database.")

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="POSTGRES_TEST_DATABASE_URL is required for Stage 9 integrity tests",
)


@pytest.fixture(scope="module")
def pg_sessions() -> Generator[sessionmaker[Session], None, None]:
    assert POSTGRES_URL is not None
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_migration_0010_upgrades_and_downgrades_cleanly() -> None:
    assert POSTGRES_URL is not None
    os.environ["DATABASE_URL"] = POSTGRES_URL
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    engine = create_engine(POSTGRES_URL)

    command.upgrade(config, "0010_stage9_notifications")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name = 'notification_events'"
                )
            ).scalar_one()
            == 1
        )

    command.downgrade(config, "0009_stage7_ai_assistant")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name = 'notification_events'"
                )
            ).scalar_one()
            == 0
        )

    command.upgrade(config, "head")
    engine.dispose()


def test_notification_event_dedupe_constraint_is_database_enforced(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        user, organization, account = _tenant(db)
        finding, _ = _finding(db, organization, account, user)
        db.commit()

        event = NotificationEvent(
            organization_id=organization.id,
            source_event_type="security.finding.created",
            source_resource_type="finding",
            source_resource_id=finding.id,
            channel=NotificationChannel.EMAIL,
            template_key="critical_finding_created",
            payload_hash=_hash(f"{organization.id}:{finding.id}"),
        )
        db.add(event)
        db.commit()

        # Identical (organization, source_event_type, source_resource_id,
        # channel, template_key) is rejected even though the payload hash
        # differs, proving the dedupe key -- not the hash -- is authoritative.
        duplicate = NotificationEvent(
            organization_id=organization.id,
            source_event_type="security.finding.created",
            source_resource_type="finding",
            source_resource_id=finding.id,
            channel=NotificationChannel.EMAIL,
            template_key="critical_finding_created",
            payload_hash=_hash(f"{organization.id}:{finding.id}:second"),
        )
        db.add(duplicate)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_notification_event_dedupe_key_distinguishes_source_event_type(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        user, organization, account = _tenant(db)
        finding, _ = _finding(db, organization, account, user)
        db.commit()

        db.add(
            NotificationEvent(
                organization_id=organization.id,
                source_event_type="security.finding.created",
                source_resource_type="finding",
                source_resource_id=finding.id,
                channel=NotificationChannel.EMAIL,
                template_key="critical_finding_created",
                payload_hash=_hash(f"{organization.id}:{finding.id}:created"),
            )
        )
        db.commit()

        # Same organization/resource/channel/template but a different
        # source_event_type is a distinct, legal row under the strengthened
        # five-column dedupe key.
        db.add(
            NotificationEvent(
                organization_id=organization.id,
                source_event_type="security.finding.reopened",
                source_resource_type="finding",
                source_resource_id=finding.id,
                channel=NotificationChannel.EMAIL,
                template_key="critical_finding_created",
                payload_hash=_hash(f"{organization.id}:{finding.id}:reopened"),
            )
        )
        db.commit()

        rows = db.scalars(
            select(NotificationEvent).where(
                NotificationEvent.organization_id == organization.id,
                NotificationEvent.source_resource_id == finding.id,
            )
        ).all()
        assert len(rows) == 2
        assert {row.source_event_type for row in rows} == {
            "security.finding.created",
            "security.finding.reopened",
        }


def test_notification_event_status_lifecycle_constraint_is_database_enforced(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        user, organization, account = _tenant(db)
        finding, _ = _finding(db, organization, account, user)
        db.commit()

        # PENDING_APPROVAL with a populated approved_at violates the lifecycle
        # constraint: approval timestamps must not exist before approval.
        event = NotificationEvent(
            organization_id=organization.id,
            source_event_type="security.finding.created",
            source_resource_type="finding",
            source_resource_id=finding.id,
            channel=NotificationChannel.EMAIL,
            template_key="critical_finding_created",
            payload_hash=_hash(str(finding.id)),
            status=NotificationStatus.PENDING_APPROVAL,
            approved_at=datetime.now(UTC),
        )
        db.add(event)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_notification_event_delivered_requires_approval_fields(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        user, organization, account = _tenant(db)
        finding, _ = _finding(db, organization, account, user)
        db.commit()

        # DELIVERED without approved_at must be rejected: delivery must never
        # occur before approval, enforced at the database.
        event = NotificationEvent(
            organization_id=organization.id,
            source_event_type="security.finding.created",
            source_resource_type="finding",
            source_resource_id=finding.id,
            channel=NotificationChannel.EMAIL,
            template_key="critical_finding_created",
            payload_hash=_hash(str(finding.id)),
            status=NotificationStatus.DELIVERED,
            delivered_at=datetime.now(UTC),
        )
        db.add(event)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_notification_event_delivered_with_null_approver_is_legal(
    pg_sessions: sessionmaker[Session],
) -> None:
    """approved_by_user_id may legally be NULL on a DELIVERED row, since the
    approving user can be deleted (ON DELETE SET NULL) after delivery. Only
    approved_at, not approved_by_user_id, is required by the lifecycle
    constraint once a row has left PENDING_APPROVAL."""
    with pg_sessions() as db:
        user, organization, account = _tenant(db)
        finding, _ = _finding(db, organization, account, user)
        db.commit()

        now = datetime.now(UTC)
        event = NotificationEvent(
            organization_id=organization.id,
            source_event_type="security.finding.created",
            source_resource_type="finding",
            source_resource_id=finding.id,
            channel=NotificationChannel.EMAIL,
            template_key="critical_finding_created",
            payload_hash=_hash(str(finding.id)),
            status=NotificationStatus.DELIVERED,
            approved_at=now,
            approved_by_user_id=None,
            delivered_at=now,
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        assert event.status == NotificationStatus.DELIVERED
        assert event.approved_by_user_id is None


def test_notification_event_survives_approver_deletion_with_approver_set_null(
    pg_sessions: sessionmaker[Session],
) -> None:
    """Deleting the user who approved a notification must SET NULL on
    approved_by_user_id and must not delete or otherwise corrupt the
    APPROVED/DELIVERED notification row itself.

    The approver here is deliberately a standalone user created directly via
    the User model, not through _tenant(): _tenant() also creates an
    Organization and AWSAccount owned by that user (created_by_user_id is
    ON DELETE RESTRICT on both), and _finding() attaches an EvaluationJob
    with started_by_user_id, also ON DELETE RESTRICT. Any of those would
    block the DELETE before it ever reached notification_events, so the
    approver here owns nothing and has no RESTRICT-guarded references.
    """
    with pg_sessions() as db:
        user, organization, account = _tenant(db)
        finding, _ = _finding(db, organization, account, user)
        marker = uuid.uuid4().hex
        approver = User(
            email=f"approver-{marker}@example.com",
            normalized_email=f"approver-{marker}@example.com",
            password_hash="test-only-hash",
            full_name="Standalone Approver",
        )
        db.add(approver)
        db.commit()

        now = datetime.now(UTC)
        event = NotificationEvent(
            organization_id=organization.id,
            source_event_type="security.finding.created",
            source_resource_type="finding",
            source_resource_id=finding.id,
            channel=NotificationChannel.EMAIL,
            template_key="critical_finding_created",
            payload_hash=_hash(str(finding.id)),
            status=NotificationStatus.DELIVERED,
            approved_at=now,
            approved_by_user_id=approver.id,
            delivered_at=now,
        )
        db.add(event)
        db.commit()
        event_id = event.id

        db.execute(text("DELETE FROM users WHERE id = :id"), {"id": approver.id})
        db.commit()
        # pg_sessions uses expire_on_commit=False, so the already-loaded
        # `event` instance would otherwise satisfy db.get() from the identity
        # map with its stale approved_by_user_id rather than re-querying the
        # row PostgreSQL just updated via ON DELETE SET NULL.
        db.expire_all()

        preserved = db.get(NotificationEvent, event_id)
        assert preserved is not None
        assert preserved.status == NotificationStatus.DELIVERED
        assert preserved.approved_by_user_id is None
        assert preserved.approved_at is not None
        assert preserved.delivered_at is not None


def test_notification_event_attempt_count_is_bounded(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        user, organization, account = _tenant(db)
        finding, _ = _finding(db, organization, account, user)
        db.commit()

        event = NotificationEvent(
            organization_id=organization.id,
            source_event_type="security.finding.created",
            source_resource_type="finding",
            source_resource_id=finding.id,
            channel=NotificationChannel.EMAIL,
            template_key="critical_finding_created",
            payload_hash=_hash(str(finding.id)),
            attempt_count=4,
        )
        db.add(event)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_notification_event_cross_tenant_isolation(
    pg_sessions: sessionmaker[Session],
) -> None:
    with pg_sessions() as db:
        user_a, org_a, account_a = _tenant(db)
        user_b, org_b, account_b = _tenant(db)
        finding_a, _ = _finding(db, org_a, account_a, user_a)
        finding_b, _ = _finding(db, org_b, account_b, user_b)
        db.commit()

        db.add(
            NotificationEvent(
                organization_id=org_a.id,
                source_event_type="security.finding.created",
                source_resource_type="finding",
                source_resource_id=finding_a.id,
                channel=NotificationChannel.EMAIL,
                template_key="critical_finding_created",
                payload_hash=_hash(str(finding_a.id)),
            )
        )
        db.add(
            NotificationEvent(
                organization_id=org_b.id,
                source_event_type="security.finding.created",
                source_resource_type="finding",
                source_resource_id=finding_b.id,
                channel=NotificationChannel.EMAIL,
                template_key="critical_finding_created",
                payload_hash=_hash(str(finding_b.id)),
            )
        )
        db.commit()

        org_a_events = db.scalars(
            select(NotificationEvent).where(NotificationEvent.organization_id == org_a.id)
        ).all()
        org_b_events = db.scalars(
            select(NotificationEvent).where(NotificationEvent.organization_id == org_b.id)
        ).all()
        assert len(org_a_events) == 1
        assert len(org_b_events) == 1
        assert org_a_events[0].organization_id != org_b_events[0].organization_id
        assert {event.id for event in org_a_events}.isdisjoint({event.id for event in org_b_events})
