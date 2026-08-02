from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event, Lock
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.exceptions.errors import AppError, ConflictError
from app.models import (
    Asset,
    AuditEvent,
    AWSAccount,
    AWSExternalIDReservation,
    DiscoveryJob,
    EvaluationJob,
    Finding,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    RefreshTokenSession,
    User,
)
from app.models.enums import (
    AssetType,
    AWSAccountStatus,
    DiscoveryJobStatus,
    EvaluationJobStatus,
    FindingSeverity,
    FindingStatus,
    InvitationStatus,
    MembershipStatus,
    OrganizationRole,
)
from app.security.passwords import hash_password
from app.security.tokens import hash_opaque_token
from app.security_rules import default_registry
from app.security_rules.base import RuleContext
from app.services.auth import AuthService, IssuedTokens
from app.services.aws_onboarding import AWSOnboardingService
from app.services.common import now_utc
from app.services.discovery import DiscoveryOrchestrator, NormalizedAsset
from app.services.evaluations import EvaluationService
from app.services.invitations import InvitationService
from app.services.organizations import OrganizationService
from app.services.remediation_admin import RemediationAdminService

POSTGRES_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
if POSTGRES_TEST_DATABASE_URL:
    database_name = make_url(POSTGRES_TEST_DATABASE_URL).database or ""
else:
    database_name = ""

if POSTGRES_TEST_DATABASE_URL and not (
    database_name == "cloudops_test" or database_name.startswith("cloudops_e2e_")
):
    raise RuntimeError(
        "POSTGRES_TEST_DATABASE_URL must target cloudops_test or a cloudops_e2e_* database"
    )

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_DATABASE_URL,
    reason="POSTGRES_TEST_DATABASE_URL is required for PostgreSQL concurrency tests",
)


@pytest.fixture(scope="module")
def postgres_engine() -> Generator[Engine, None, None]:
    assert POSTGRES_TEST_DATABASE_URL is not None
    engine = create_engine(POSTGRES_TEST_DATABASE_URL, pool_pre_ping=True)
    expected = {
        "users",
        "organizations",
        "organization_members",
        "organization_invitations",
        "refresh_token_sessions",
        "audit_events",
        "aws_accounts",
        "aws_external_id_reservations",
        "assets",
        "discovery_jobs",
    }
    with engine.connect() as connection:
        tables = set(
            connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )
    assert expected <= tables, "Run `alembic upgrade head` against the disposable database first"
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def postgres_sessions(postgres_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=postgres_engine, expire_on_commit=False)


@pytest.fixture(scope="module")
def postgres_settings() -> Settings:
    assert POSTGRES_TEST_DATABASE_URL is not None
    return Settings(
        app_env="testing",
        database_url=SecretStr(POSTGRES_TEST_DATABASE_URL),
        jwt_secret_key=SecretStr("postgres-concurrency-test-secret-at-least-32-characters"),
    )


def _user(email: str) -> User:
    return User(
        email=email,
        normalized_email=email,
        password_hash=hash_password("Strong-Password-123!"),
        full_name=email.split("@", 1)[0],
    )


def _run_concurrently(first: Callable[[], object], second: Callable[[], object]) -> list[object]:
    barrier = Barrier(2)

    def synchronized(operation: Callable[[], object]) -> object:
        barrier.wait(timeout=5)
        return operation()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(synchronized, first), executor.submit(synchronized, second)]
        results: list[object] = []
        for future in futures:
            try:
                results.append(future.result(timeout=15))
            except Exception as exc:
                results.append(exc)
        return results


def test_concurrent_discovery_start_and_asset_identity_invariants(
    postgres_sessions: sessionmaker[Session],
    postgres_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with postgres_sessions.begin() as db:
        owner = _user(f"discovery-owner-{uuid.uuid4()}@example.com")
        db.add(owner)
        db.flush()
        organization = Organization(
            name="Discovery concurrency",
            slug=f"discovery-{uuid.uuid4()}",
            created_by_user_id=owner.id,
        )
        db.add(organization)
        db.flush()
        db.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=owner.id,
                role=OrganizationRole.OWNER,
                status=MembershipStatus.ACTIVE,
                joined_at=now_utc(),
            )
        )
        account = AWSAccount(
            organization_id=organization.id,
            name="Production",
            account_id="123456789012",
            role_arn="arn:aws:iam::123456789012:role/CloudOpsReadOnlyRole",
            external_id=f"cloudops-{uuid.uuid4()}",
            status=AWSAccountStatus.CONNECTED,
            connection_status=AWSAccountStatus.CONNECTED,
            created_by_user_id=owner.id,
        )
        db.add(account)
        db.flush()
        owner_id, organization_id, account_id = owner.id, organization.id, account.id

    def do_not_run(
        orchestrator: DiscoveryOrchestrator, job_id: uuid.UUID, _actor: User
    ) -> DiscoveryJob:
        job = orchestrator.db.get(DiscoveryJob, job_id)
        assert job is not None
        return job

    monkeypatch.setattr(DiscoveryOrchestrator, "run", do_not_run)

    def start() -> DiscoveryJob:
        with postgres_sessions() as db:
            actor = db.get(User, owner_id)
            assert actor is not None
            return DiscoveryOrchestrator(db, postgres_settings).start(account_id, actor)

    results = _run_concurrently(start, start)
    assert len([item for item in results if isinstance(item, DiscoveryJob)]) == 1
    assert len([item for item in results if isinstance(item, AppError)]) == 1
    with postgres_sessions() as db:
        active_jobs = db.scalar(
            select(func.count())
            .select_from(DiscoveryJob)
            .where(DiscoveryJob.aws_account_id == account_id)
        )
        indexes = set(
            db.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename IN ('assets','discovery_jobs')"
                )
            ).scalars()
        )
        assert active_jobs == 1
        assert "uq_active_discovery_job_account" in indexes
        assert "uq_asset_identity" in indexes

    def insert_asset(resource_name: str) -> uuid.UUID:
        with postgres_sessions.begin() as db:
            item = Asset(
                organization_id=organization_id,
                aws_account_id=account_id,
                asset_type=AssetType.EC2_INSTANCE,
                resource_id=resource_name,
                name=resource_name,
                region="us-east-1",
            )
            db.add(item)
            db.flush()
            return item.id

    identity = f"i-{uuid.uuid4()}"
    upserts = _run_concurrently(lambda: insert_asset(identity), lambda: insert_asset(identity))
    assert len([item for item in upserts if isinstance(item, uuid.UUID)]) == 1
    assert len([item for item in upserts if isinstance(item, IntegrityError)]) == 1


def test_only_one_concurrent_refresh_succeeds(
    postgres_sessions: sessionmaker[Session], postgres_settings: Settings
) -> None:
    raw = f"refresh-{uuid.uuid4()}"
    family_id = uuid.uuid4()
    with postgres_sessions.begin() as db:
        user = _user(f"refresh-{uuid.uuid4()}@example.com")
        db.add(user)
        db.flush()
        original = RefreshTokenSession(
            user_id=user.id,
            token_hash=hash_opaque_token(raw),
            family_id=family_id,
            issued_at=now_utc(),
            expires_at=now_utc() + timedelta(days=1),
        )
        db.add(original)
        db.flush()
        original_id = original.id

    def rotate() -> IssuedTokens:
        with postgres_sessions() as db:
            return AuthService(db, postgres_settings).refresh(raw, "pytest", "127.0.0.1")

    results = _run_concurrently(rotate, rotate)
    successes = [item for item in results if isinstance(item, IssuedTokens)]
    failures = [item for item in results if isinstance(item, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1

    with postgres_sessions() as db:
        sessions = list(
            db.scalars(
                select(RefreshTokenSession).where(RefreshTokenSession.family_id == family_id)
            )
        )
        loaded_original = db.get(RefreshTokenSession, original_id)
        assert len(sessions) == 2
        assert loaded_original is not None and loaded_original.replaced_by_id is not None
        assert any(item.id == loaded_original.replaced_by_id for item in sessions)
        assert all(item.revoked_at is not None for item in sessions)


def test_concurrent_invitation_acceptance_creates_one_membership(
    postgres_sessions: sessionmaker[Session], postgres_settings: Settings
) -> None:
    raw = f"invitation-{uuid.uuid4()}"
    with postgres_sessions.begin() as db:
        inviter = _user(f"inviter-{uuid.uuid4()}@example.com")
        invitee = _user(f"invitee-{uuid.uuid4()}@example.com")
        db.add_all([inviter, invitee])
        db.flush()
        organization = Organization(
            name="Invitation concurrency",
            slug=f"invitation-{uuid.uuid4()}",
            created_by_user_id=inviter.id,
        )
        db.add(organization)
        db.flush()
        invitation = OrganizationInvitation(
            organization_id=organization.id,
            email=invitee.email,
            normalized_email=invitee.normalized_email,
            role=OrganizationRole.VIEWER,
            token_hash=hash_opaque_token(raw),
            status=InvitationStatus.PENDING,
            invited_by_user_id=inviter.id,
            expires_at=now_utc() + timedelta(hours=1),
        )
        db.add(invitation)
        invitee_id = invitee.id
        organization_id = organization.id

    def accept() -> uuid.UUID:
        with postgres_sessions() as db:
            invitee = db.get(User, invitee_id)
            assert invitee is not None
            membership = InvitationService(db, postgres_settings).accept(raw, invitee)
            return membership.id

    results = _run_concurrently(accept, accept)
    assert not [item for item in results if isinstance(item, Exception)]
    assert len(set(results)) == 1
    with postgres_sessions() as db:
        count = db.scalar(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == invitee_id,
            )
        )
        loaded_invitation = db.scalar(
            select(OrganizationInvitation).where(
                OrganizationInvitation.token_hash == hash_opaque_token(raw)
            )
        )
        assert count == 1
        assert loaded_invitation is not None
        assert loaded_invitation.status == InvitationStatus.ACCEPTED


def test_pending_invitation_partial_index_uses_persisted_enum_values(
    postgres_sessions: sessionmaker[Session],
) -> None:
    email = f"partial-index-{uuid.uuid4()}@example.com"
    with postgres_sessions.begin() as db:
        inviter = _user(f"partial-owner-{uuid.uuid4()}@example.com")
        db.add(inviter)
        db.flush()
        organization = Organization(
            name="Partial index verification",
            slug=f"partial-index-{uuid.uuid4()}",
            created_by_user_id=inviter.id,
        )
        db.add(organization)
        db.flush()
        first = OrganizationInvitation(
            organization_id=organization.id,
            email=email,
            normalized_email=email,
            role=OrganizationRole.VIEWER,
            token_hash=hash_opaque_token(f"first-{uuid.uuid4()}"),
            status=InvitationStatus.PENDING,
            invited_by_user_id=inviter.id,
            expires_at=now_utc() + timedelta(hours=1),
        )
        db.add(first)
        db.flush()
        organization_id = organization.id
        first_id = first.id

    with pytest.raises(IntegrityError), postgres_sessions.begin() as db:
        db.add(
            OrganizationInvitation(
                organization_id=organization_id,
                email=email,
                normalized_email=email,
                role=OrganizationRole.AUDITOR,
                token_hash=hash_opaque_token(f"duplicate-{uuid.uuid4()}"),
                status=InvitationStatus.PENDING,
                invited_by_user_id=inviter.id,
                expires_at=now_utc() + timedelta(hours=1),
            )
        )
        db.flush()

    with postgres_sessions.begin() as db:
        persisted = db.execute(
            text("SELECT status FROM organization_invitations WHERE id = :id"),
            {"id": first_id},
        ).scalar_one()
        assert persisted == "pending"
        persisted_first = db.get(OrganizationInvitation, first_id)
        assert persisted_first is not None
        persisted_first.status = InvitationStatus.CANCELLED

    with postgres_sessions.begin() as db:
        db.add(
            OrganizationInvitation(
                organization_id=organization_id,
                email=email,
                normalized_email=email,
                role=OrganizationRole.VIEWER,
                token_hash=hash_opaque_token(f"replacement-{uuid.uuid4()}"),
                status=InvitationStatus.PENDING,
                invited_by_user_id=inviter.id,
                expires_at=now_utc() + timedelta(hours=1),
            )
        )


@pytest.mark.parametrize("operation", ["demote", "suspend", "remove"])
def test_concurrent_owner_changes_preserve_one_active_owner(
    postgres_sessions: sessionmaker[Session], operation: str
) -> None:
    with postgres_sessions.begin() as db:
        first_user = _user(f"owner-a-{operation}-{uuid.uuid4()}@example.com")
        second_user = _user(f"owner-b-{operation}-{uuid.uuid4()}@example.com")
        db.add_all([first_user, second_user])
        db.flush()
        organization = Organization(
            name=f"Owner concurrency {operation}",
            slug=f"owner-{operation}-{uuid.uuid4()}",
            created_by_user_id=first_user.id,
        )
        db.add(organization)
        db.flush()
        memberships = [
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role=OrganizationRole.OWNER,
                status=MembershipStatus.ACTIVE,
                joined_at=now_utc(),
            )
            for user in (first_user, second_user)
        ]
        db.add_all(memberships)
        db.flush()
        organization_id = organization.id
        targets = [(first_user.id, memberships[0].id), (second_user.id, memberships[1].id)]

    def change(target: tuple[uuid.UUID, uuid.UUID]) -> object:
        user_id, membership_id = target
        with postgres_sessions() as db:
            actor = db.get(User, user_id)
            assert actor is not None
            service = OrganizationService(db)
            if operation == "demote":
                return service.change_role(
                    organization_id, membership_id, actor, OrganizationRole.VIEWER
                )
            if operation == "suspend":
                return service.change_status(
                    organization_id, membership_id, actor, MembershipStatus.SUSPENDED
                )
            service.remove(organization_id, membership_id, actor)
            return membership_id

    results = _run_concurrently(lambda: change(targets[0]), lambda: change(targets[1]))
    assert len([item for item in results if isinstance(item, AppError)]) == 1
    assert len([item for item in results if not isinstance(item, Exception)]) == 1
    with postgres_sessions() as db:
        active_owners = db.scalar(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.role == OrganizationRole.OWNER,
                OrganizationMembership.status == MembershipStatus.ACTIVE,
            )
        )
        isolation = db.execute(text("SHOW transaction_isolation")).scalar_one()
        assert isolation == "read committed"
        assert active_owners == 1


def _create_managed_account(
    sessions: sessionmaker[Session],
    settings: Settings,
    *,
    suffix: str,
    provider_account_id: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    with sessions() as db:
        owner = _user(f"aws-lifecycle-{suffix}-{uuid.uuid4()}@example.com")
        db.add(owner)
        db.flush()
        organization = Organization(
            name=f"AWS lifecycle {suffix}",
            slug=f"aws-lifecycle-{suffix}-{uuid.uuid4()}",
            created_by_user_id=owner.id,
        )
        db.add(organization)
        db.flush()
        db.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=owner.id,
                role=OrganizationRole.OWNER,
                status=MembershipStatus.ACTIVE,
                joined_at=now_utc(),
            )
        )
        db.commit()
        account = AWSOnboardingService(db, settings).create_account(
            organization.id, owner, f"Account {suffix}", provider_account_id
        )
        account = AWSOnboardingService(db, settings).update_role(
            account.id,
            owner,
            f"arn:aws:iam::{provider_account_id}:role/CloudOpsReadOnlyRole",
        )
        return owner.id, organization.id, account.id


def test_external_id_reservations_are_permanent_and_concurrency_safe(
    postgres_sessions: sessionmaker[Session],
    postgres_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with postgres_sessions() as db:
        owner = _user(f"reservation-owner-{uuid.uuid4()}@example.com")
        db.add(owner)
        db.flush()
        organization = Organization(
            name="Reservation concurrency",
            slug=f"reservation-concurrency-{uuid.uuid4()}",
            created_by_user_id=owner.id,
        )
        db.add(organization)
        db.flush()
        db.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=owner.id,
                role=OrganizationRole.OWNER,
                status=MembershipStatus.ACTIVE,
                joined_at=now_utc(),
            )
        )
        db.commit()
        owner_id, organization_id = owner.id, organization.id

    calls, calls_lock, first_pair = 0, Lock(), Barrier(2)

    def colliding_generator() -> str:
        nonlocal calls
        with calls_lock:
            calls += 1
            number = calls
        if number <= 2:
            first_pair.wait(timeout=5)
            return "cloudops-concurrent-shared"
        return f"cloudops-concurrent-{uuid.uuid4()}"

    monkeypatch.setattr(
        AWSOnboardingService,
        "generate_external_id",
        staticmethod(colliding_generator),
    )

    def create(provider_id: str) -> AWSAccount:
        with postgres_sessions() as db:
            owner = db.get(User, owner_id)
            assert owner is not None
            return AWSOnboardingService(db, postgres_settings).create_account(
                organization_id, owner, provider_id, provider_id
            )

    results = _run_concurrently(lambda: create("111122223333"), lambda: create("444455556666"))
    assert not [item for item in results if isinstance(item, Exception)]
    with postgres_sessions() as db:
        reservations = list(
            db.scalars(
                select(AWSExternalIDReservation).where(
                    AWSExternalIDReservation.organization_id == organization_id
                )
            )
        )
        assert len(reservations) == 2
        assert len({item.external_id for item in reservations}) == 2
        account = db.scalar(select(AWSAccount).where(AWSAccount.organization_id == organization_id))
        assert account is not None
        AWSOnboardingService(db, postgres_settings).delete_account(
            account.id,
            db.get(User, owner_id),  # type: ignore[arg-type]
        )
        retired = db.scalar(
            select(AWSExternalIDReservation).where(
                AWSExternalIDReservation.external_id == account.external_id
            )
        )
        assert retired is not None and retired.aws_account_id is None
        with pytest.raises(DBAPIError):
            db.delete(retired)
            db.commit()
        db.rollback()


def test_validation_and_disconnect_lifecycle_concurrency(
    postgres_sessions: sessionmaker[Session],
    postgres_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id, _organization_id, account_id = _create_managed_account(
        postgres_sessions,
        postgres_settings,
        suffix="validation",
        provider_account_id="777788889999",
    )
    entered, release = Event(), Event()

    def blocked_assume(_self: AWSOnboardingService, account: AWSAccount) -> str:
        entered.set()
        assert release.wait(timeout=10)
        return account.account_id

    monkeypatch.setattr(AWSOnboardingService, "assume_role", blocked_assume)

    def validate() -> object:
        with postgres_sessions() as db:
            actor = db.get(User, owner_id)
            assert actor is not None
            return AWSOnboardingService(db, postgres_settings).validate_connection(
                account_id, actor
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(validate)
        assert entered.wait(timeout=10)
        second = executor.submit(validate)
        second_result: object
        try:
            second_result = second.result(timeout=10)
        except Exception as exc:
            second_result = exc
        release.set()
        first_result = first.result(timeout=10)
    assert isinstance(first_result, AWSAccount)
    assert isinstance(second_result, AppError)

    def disconnect() -> object:
        with postgres_sessions() as db:
            actor = db.get(User, owner_id)
            assert actor is not None
            return AWSOnboardingService(db, postgres_settings).disconnect_account(account_id, actor)

    disconnects = _run_concurrently(disconnect, disconnect)
    assert not [item for item in disconnects if isinstance(item, Exception)]
    with postgres_sessions() as db:
        terminal_validations = db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.resource_id == account_id,
                AuditEvent.event_type.in_(
                    ("aws.account.validation_succeeded", "aws.account.validation_failed")
                ),
            )
        )
        disconnect_events = db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.resource_id == account_id,
                AuditEvent.event_type == "aws.account.disconnected",
            )
        )
        assert terminal_validations == 1
        assert disconnect_events == 1


@pytest.mark.parametrize("mutation", ["disconnect", "update", "delete"])
def test_validation_result_cannot_overwrite_newer_lifecycle_mutation(
    postgres_sessions: sessionmaker[Session],
    postgres_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    provider_id = {
        "disconnect": "101010101010",
        "update": "202020202020",
        "delete": "303030303030",
    }[mutation]
    owner_id, _organization_id, account_id = _create_managed_account(
        postgres_sessions,
        postgres_settings,
        suffix=mutation,
        provider_account_id=provider_id,
    )
    entered, release = Event(), Event()

    def blocked_assume(_self: AWSOnboardingService, account: AWSAccount) -> str:
        entered.set()
        assert release.wait(timeout=10)
        return account.account_id

    monkeypatch.setattr(AWSOnboardingService, "assume_role", blocked_assume)

    def validate() -> object:
        with postgres_sessions() as db:
            actor = db.get(User, owner_id)
            assert actor is not None
            return AWSOnboardingService(db, postgres_settings).validate_connection(
                account_id, actor
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(validate)
        assert entered.wait(timeout=10)
        with postgres_sessions() as db:
            actor = db.get(User, owner_id)
            assert actor is not None
            service = AWSOnboardingService(db, postgres_settings)
            if mutation == "disconnect":
                service.disconnect_account(account_id, actor)
            elif mutation == "update":
                service.update_account(account_id, actor, name="Newer name", role_arn=None)
            else:
                service.delete_account(account_id, actor)
        release.set()
        try:
            validation_result: object = future.result(timeout=10)
        except Exception as exc:
            validation_result = exc
    assert isinstance(validation_result, AppError)
    with postgres_sessions() as db:
        account = db.get(AWSAccount, account_id)
        terminal_count = db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.resource_id == account_id,
                AuditEvent.event_type.in_(
                    ("aws.account.validation_succeeded", "aws.account.validation_failed")
                ),
            )
        )
        assert terminal_count == 0
        if mutation == "disconnect":
            assert account is not None
            assert account.connection_status == AWSAccountStatus.DISCONNECTED
        elif mutation == "update":
            assert account is not None and account.name == "Newer name"
        else:
            assert account is None
            reservation = db.scalar(
                select(AWSExternalIDReservation).where(
                    AWSExternalIDReservation.retired_at.is_not(None)
                )
            )
            assert reservation is not None


def test_postgres_stage3_tenant_and_lifecycle_constraints(
    postgres_sessions: sessionmaker[Session],
) -> None:
    with postgres_sessions.begin() as db:
        user = _user(f"integrity-{uuid.uuid4()}@example.com")
        db.add(user)
        db.flush()
        first = Organization(
            name="Integrity first",
            slug=f"integrity-first-{uuid.uuid4()}",
            created_by_user_id=user.id,
        )
        second = Organization(
            name="Integrity second",
            slug=f"integrity-second-{uuid.uuid4()}",
            created_by_user_id=user.id,
        )
        db.add_all([first, second])
        db.flush()
        account = AWSAccount(
            organization_id=first.id,
            name="Integrity account",
            account_id="909090909090",
            external_id=f"cloudops-{uuid.uuid4()}",
            created_by_user_id=user.id,
        )
        db.add(account)
        db.flush()
        user_id, first_id, second_id, account_id = user.id, first.id, second.id, account.id

    with postgres_sessions.begin() as db:
        db.add(
            Asset(
                organization_id=first_id,
                aws_account_id=account_id,
                asset_type=AssetType.EC2_INSTANCE,
                resource_id="valid",
                name="valid",
                region="us-east-1",
            )
        )

    with pytest.raises(IntegrityError), postgres_sessions.begin() as db:
        db.add(
            Asset(
                organization_id=second_id,
                aws_account_id=account_id,
                asset_type=AssetType.EC2_INSTANCE,
                resource_id="cross-tenant",
                name="cross-tenant",
                region="us-east-1",
            )
        )
        db.flush()
    with pytest.raises(IntegrityError), postgres_sessions.begin() as db:
        db.add(
            DiscoveryJob(
                organization_id=second_id,
                aws_account_id=account_id,
                started_by_user_id=user_id,
            )
        )
        db.flush()
    with pytest.raises(IntegrityError), postgres_sessions.begin() as db:
        db.add(
            Asset(
                organization_id=first_id,
                aws_account_id=account_id,
                asset_type=AssetType.S3_BUCKET,
                resource_id="backwards",
                name="backwards",
                region="global",
                first_seen_at=datetime(2026, 1, 2, tzinfo=UTC),
                last_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        db.flush()
    for values in (
        {"assets_discovered": -1},
        {"assets_created": -1},
        {"assets_updated": -1},
        {"assets_deactivated": -1},
    ):
        with pytest.raises(IntegrityError), postgres_sessions.begin() as db:
            db.add(
                DiscoveryJob(
                    organization_id=first_id,
                    aws_account_id=account_id,
                    started_by_user_id=user_id,
                    **values,
                )
            )
            db.flush()
    invalid_jobs = (
        DiscoveryJob(
            organization_id=first_id,
            aws_account_id=account_id,
            started_by_user_id=user_id,
            status=DiscoveryJobStatus.COMPLETED,
            started_at=now_utc(),
        ),
        DiscoveryJob(
            organization_id=first_id,
            aws_account_id=account_id,
            started_by_user_id=user_id,
            status=DiscoveryJobStatus.RUNNING,
            started_at=now_utc(),
            finished_at=now_utc(),
        ),
    )
    for invalid in invalid_jobs:
        with pytest.raises(IntegrityError), postgres_sessions.begin() as db:
            db.add(invalid)
            db.flush()

    with postgres_sessions.begin() as db:
        job = DiscoveryJob(
            organization_id=first_id,
            aws_account_id=account_id,
            started_by_user_id=user_id,
        )
        db.add(job)
        db.flush()
        job.status = DiscoveryJobStatus.RUNNING
        job.started_at = now_utc()
        db.flush()
        job.status = DiscoveryJobStatus.COMPLETED
        job.finished_at = now_utc()
        db.flush()


def test_different_accounts_discover_and_actual_upserts_serialize_safely(
    postgres_sessions: sessionmaker[Session],
    postgres_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_owner, _first_org, first_account = _create_managed_account(
        postgres_sessions,
        postgres_settings,
        suffix="discovery-a",
        provider_account_id="414141414141",
    )
    second_owner, _second_org, second_account = _create_managed_account(
        postgres_sessions,
        postgres_settings,
        suffix="discovery-b",
        provider_account_id="424242424242",
    )
    with postgres_sessions.begin() as db:
        for account_id in (first_account, second_account):
            account = db.get(AWSAccount, account_id)
            assert account is not None
            account.status = account.connection_status = AWSAccountStatus.CONNECTED

    monkeypatch.setattr(DiscoveryOrchestrator, "services", ())
    monkeypatch.setattr(DiscoveryOrchestrator, "_assumed_client_factory", lambda *_args: object())

    def start(owner_id: uuid.UUID, account_id: uuid.UUID) -> DiscoveryJob:
        with postgres_sessions() as db:
            actor = db.get(User, owner_id)
            assert actor is not None
            return DiscoveryOrchestrator(db, postgres_settings).start(account_id, actor)

    starts = _run_concurrently(
        lambda: start(first_owner, first_account),
        lambda: start(second_owner, second_account),
    )
    assert len([item for item in starts if isinstance(item, DiscoveryJob)]) == 2
    assert all(
        item.status == DiscoveryJobStatus.COMPLETED
        for item in starts
        if isinstance(item, DiscoveryJob)
    )

    def upsert(resource_id: str, status: str) -> tuple[int, int, int]:
        with postgres_sessions() as db:
            account = db.get(AWSAccount, first_account)
            assert account is not None
            result = DiscoveryOrchestrator(db, postgres_settings)._upsert(
                account,
                [
                    NormalizedAsset(
                        asset_type=AssetType.EC2_INSTANCE,
                        resource_id=resource_id,
                        arn=f"arn:aws:ec2:::instance/{resource_id}",
                        name=resource_id,
                        region="us-east-1",
                        status=status,
                        tags={},
                        metadata={"writer": status},
                    )
                ],
                {AssetType.EC2_INSTANCE},
            )
            db.commit()
            return result

    same = _run_concurrently(
        lambda: upsert("i-shared", "running"),
        lambda: upsert("i-shared", "stopped"),
    )
    assert not [item for item in same if isinstance(item, Exception)]
    different = _run_concurrently(
        lambda: upsert("i-first", "running"),
        lambda: upsert("i-second", "running"),
    )
    assert not [item for item in different if isinstance(item, Exception)]
    with postgres_sessions() as db:
        shared = list(
            db.scalars(
                select(Asset).where(
                    Asset.aws_account_id == first_account,
                    Asset.resource_id == "i-shared",
                )
            )
        )
        assert len(shared) == 1
        assert shared[0].last_seen_at >= shared[0].first_seen_at
        assert shared[0].metadata_json["writer"] == shared[0].status
        assert (
            db.scalar(
                select(func.count())
                .select_from(Asset)
                .where(
                    Asset.aws_account_id == first_account,
                    Asset.resource_id.in_(("i-first", "i-second")),
                )
            )
            == 2
        )


def test_discovery_terminal_race_and_rollback_leave_consistent_state(
    postgres_sessions: sessionmaker[Session],
    postgres_settings: Settings,
) -> None:
    owner_id, organization_id, account_id = _create_managed_account(
        postgres_sessions,
        postgres_settings,
        suffix="terminal-race",
        provider_account_id="515151515151",
    )
    with postgres_sessions.begin() as db:
        account = db.get(AWSAccount, account_id)
        assert account is not None
        account.status = account.connection_status = AWSAccountStatus.CONNECTED
        job = DiscoveryJob(
            organization_id=organization_id,
            aws_account_id=account_id,
            started_by_user_id=owner_id,
            status=DiscoveryJobStatus.RUNNING,
            started_at=now_utc(),
        )
        db.add(job)
        db.flush()
        job_id = job.id

    def finish(status: DiscoveryJobStatus) -> DiscoveryJob:
        with postgres_sessions() as db:
            actor = db.get(User, owner_id)
            job = db.get(DiscoveryJob, job_id)
            assert actor is not None and job is not None
            return DiscoveryOrchestrator(db, postgres_settings)._finish(
                job,
                actor,
                status,
                {} if status == DiscoveryJobStatus.COMPLETED else {"ec2": "failed"},
            )

    terminal = _run_concurrently(
        lambda: finish(DiscoveryJobStatus.COMPLETED),
        lambda: finish(DiscoveryJobStatus.FAILED),
    )
    assert len([item for item in terminal if isinstance(item, DiscoveryJob)]) == 1
    assert len([item for item in terminal if isinstance(item, AppError)]) == 1
    with postgres_sessions() as db:
        stored = db.get(DiscoveryJob, job_id)
        assert stored is not None
        assert stored.status in {DiscoveryJobStatus.COMPLETED, DiscoveryJobStatus.FAILED}
        assert stored.finished_at is not None
        terminal_events = db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.resource_id == job_id,
                AuditEvent.event_type.in_(
                    (
                        "aws.discovery.completed",
                        "aws.discovery.failed",
                        "aws.discovery.partially_completed",
                    )
                ),
            )
        )
        assert terminal_events == 1

    rollback_resource = f"i-rollback-{uuid.uuid4()}"
    with postgres_sessions() as db:
        account = db.get(AWSAccount, account_id)
        assert account is not None
        DiscoveryOrchestrator(db, postgres_settings)._upsert(
            account,
            [
                NormalizedAsset(
                    asset_type=AssetType.EC2_INSTANCE,
                    resource_id=rollback_resource,
                    arn=None,
                    name=rollback_resource,
                    region="us-east-1",
                    status="running",
                    tags={},
                    metadata={},
                )
            ],
            {AssetType.EC2_INSTANCE},
        )
        db.rollback()
    with postgres_sessions() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Asset)
                .where(Asset.resource_id == rollback_resource)
            )
            == 0
        )


def _stage4_account(db: Session, suffix: str) -> tuple[User, Organization, AWSAccount, Asset]:
    owner = _user(f"evaluation-{suffix}-{uuid.uuid4()}@example.com")
    db.add(owner)
    db.flush()
    organization = Organization(
        name=f"Evaluation {suffix}",
        slug=f"evaluation-{suffix}-{uuid.uuid4()}",
        created_by_user_id=owner.id,
    )
    db.add(organization)
    db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=owner.id,
            role=OrganizationRole.OWNER,
            status=MembershipStatus.ACTIVE,
            joined_at=now_utc(),
        )
    )
    account = AWSAccount(
        organization_id=organization.id,
        name="Production",
        account_id=f"{abs(hash(suffix)) % 10**12:012d}",
        role_arn=f"arn:aws:iam::{abs(hash(suffix)) % 10**12:012d}:role/CloudOpsReadOnlyRole",
        external_id=f"cloudops-{uuid.uuid4()}",
        status=AWSAccountStatus.CONNECTED,
        connection_status=AWSAccountStatus.CONNECTED,
        created_by_user_id=owner.id,
    )
    db.add(account)
    db.flush()
    asset = Asset(
        organization_id=organization.id,
        aws_account_id=account.id,
        asset_type=AssetType.EC2_SECURITY_GROUP,
        resource_id=f"sg-{uuid.uuid4()}",
        name="public-ssh",
        region="us-east-1",
        status="active",
        tags={},
        metadata_json={
            "ip_permissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ]
        },
        first_seen_at=now_utc(),
        last_seen_at=now_utc(),
    )
    db.add(asset)
    db.flush()
    return owner, organization, account, asset


def test_stage4_concurrent_evaluation_start_and_different_accounts(
    postgres_sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    with postgres_sessions.begin() as db:
        owner_a, _organization_a, account_a, _asset_a = _stage4_account(db, "a")
        owner_b, _organization_b, account_b, _asset_b = _stage4_account(db, "b")
        owner_a_id, owner_b_id = owner_a.id, owner_b.id
        account_a_id, account_b_id = account_a.id, account_b.id

    def leave_pending(service: EvaluationService, job_id: uuid.UUID, _actor: User) -> EvaluationJob:
        job = service.db.get(EvaluationJob, job_id)
        assert job is not None
        return job

    monkeypatch.setattr(EvaluationService, "run", leave_pending)

    def start(account_id: uuid.UUID, owner_id: uuid.UUID) -> EvaluationJob:
        with postgres_sessions() as db:
            owner = db.get(User, owner_id)
            assert owner is not None
            return EvaluationService(db).start(account_id, owner)

    same = _run_concurrently(
        lambda: start(account_a_id, owner_a_id),
        lambda: start(account_a_id, owner_a_id),
    )
    assert sum(isinstance(result, EvaluationJob) for result in same) == 1
    assert sum(isinstance(result, AppError) for result in same) == 1

    with postgres_sessions.begin() as db:
        active = db.scalars(
            select(EvaluationJob).where(
                EvaluationJob.aws_account_id == account_a_id,
                EvaluationJob.status == EvaluationJobStatus.PENDING,
            )
        ).all()
        assert len(active) == 1
        active[0].status = EvaluationJobStatus.FAILED
        active[0].started_at = now_utc()
        active[0].finished_at = now_utc()

    different = _run_concurrently(
        lambda: start(account_a_id, owner_a_id),
        lambda: start(account_b_id, owner_b_id),
    )
    assert all(isinstance(result, EvaluationJob) for result in different)


def test_stage4_concurrent_finding_creation_and_cross_tenant_rejection(
    postgres_sessions: sessionmaker[Session],
) -> None:
    with postgres_sessions.begin() as db:
        owner, organization, account, asset = _stage4_account(db, "finding")
        other_owner, other_org, _other_account, _other_asset = _stage4_account(db, "other")
        job = EvaluationJob(
            organization_id=organization.id,
            aws_account_id=account.id,
            sequence=1,
            started_by_user_id=owner.id,
        )
        db.add(job)
        db.flush()
        ids = (
            organization.id,
            other_org.id,
            account.id,
            asset.id,
            job.id,
            other_owner.id,
        )

    organization_id, other_org_id, account_id, asset_id, job_id, _ = ids

    def insert_finding() -> Finding:
        with postgres_sessions.begin() as db:
            finding = Finding(
                organization_id=organization_id,
                aws_account_id=account_id,
                asset_id=asset_id,
                rule_key="EC2_SG_SSH_OPEN_TO_WORLD",
                rule_version=1,
                severity=FindingSeverity.CRITICAL,
                category="network",
                status=FindingStatus.OPEN,
                evidence_json={"cidr": "0.0.0.0/0"},
                first_seen_at=now_utc(),
                last_seen_at=now_utc(),
                last_evaluation_id=job_id,
            )
            db.add(finding)
            db.flush()
            return finding

    results = _run_concurrently(insert_finding, insert_finding)
    assert sum(isinstance(result, Finding) for result in results) == 1
    assert sum(isinstance(result, IntegrityError) for result in results) == 1
    with postgres_sessions() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Finding)
                .where(
                    Finding.asset_id == asset_id,
                    Finding.rule_key == "EC2_SG_SSH_OPEN_TO_WORLD",
                )
            )
            == 1
        )

    with pytest.raises(IntegrityError), postgres_sessions.begin() as db:
        db.add(
            Finding(
                organization_id=other_org_id,
                aws_account_id=account_id,
                asset_id=asset_id,
                rule_key="CROSS_TENANT_TEST",
                rule_version=1,
                severity=FindingSeverity.HIGH,
                category="tenant",
                status=FindingStatus.OPEN,
                evidence_json={},
                first_seen_at=now_utc(),
                last_seen_at=now_utc(),
                last_evaluation_id=job_id,
            )
        )


def test_stage4_repair_constraint_matrix(
    postgres_sessions: sessionmaker[Session],
) -> None:
    with postgres_sessions.begin() as db:
        owner, organization, account, asset = _stage4_account(db, "constraints")
        valid_job = EvaluationJob(
            organization_id=organization.id,
            aws_account_id=account.id,
            sequence=1,
            status=EvaluationJobStatus.COMPLETED,
            started_by_user_id=owner.id,
            started_at=now_utc(),
            finished_at=now_utc(),
        )
        db.add(valid_job)
        db.flush()
        ids = organization.id, account.id, asset.id, owner.id, valid_job.id

    organization_id, account_id, asset_id, owner_id, job_id = ids

    invalid_jobs: tuple[dict[str, Any], ...] = (
        {"status": EvaluationJobStatus.RUNNING, "started_at": None, "finished_at": None},
        {
            "status": EvaluationJobStatus.RUNNING,
            "started_at": now_utc(),
            "finished_at": now_utc(),
        },
        {
            "status": EvaluationJobStatus.COMPLETED,
            "started_at": now_utc(),
            "finished_at": None,
        },
        {
            "status": EvaluationJobStatus.FAILED,
            "started_at": now_utc(),
            "finished_at": now_utc(),
            "evaluation_errors": -1,
        },
        {
            "status": EvaluationJobStatus.COMPLETED,
            "started_at": now_utc(),
            "finished_at": now_utc(),
            "findings_reopened": -1,
        },
    )
    for sequence, values in enumerate(invalid_jobs, start=2):
        with pytest.raises(IntegrityError), postgres_sessions.begin() as db:
            db.add(
                EvaluationJob(
                    organization_id=organization_id,
                    aws_account_id=account_id,
                    sequence=sequence,
                    started_by_user_id=owner_id,
                    **values,
                )
            )

    now = now_utc()
    invalid_findings: tuple[dict[str, Any], ...] = (
        {
            "status": FindingStatus.RESOLVED,
            "resolved_at": None,
        },
        {
            "status": FindingStatus.SUPPRESSED,
            "suppressed_at": now,
            "suppression_reason": "Maintenance",
            "suppressed_by_user_id": None,
        },
        {
            "status": FindingStatus.SUPPRESSED,
            "suppressed_at": now,
            "suppression_reason": "",
            "suppressed_by_user_id": owner_id,
        },
        {
            "status": FindingStatus.OPEN,
            "first_seen_at": now,
            "last_seen_at": now - timedelta(seconds=1),
        },
    )
    for index, values in enumerate(invalid_findings):
        with pytest.raises(IntegrityError), postgres_sessions.begin() as db:
            finding = Finding(
                organization_id=organization_id,
                aws_account_id=account_id,
                asset_id=asset_id,
                rule_key=f"CONSTRAINT_TEST_{index}",
                rule_version=1,
                severity=FindingSeverity.HIGH,
                category="integrity",
                evidence_json={},
                first_seen_at=now,
                last_seen_at=now,
                last_evaluation_id=job_id,
            )
            for name, value in values.items():
                setattr(finding, name, value)
            db.add(finding)

    with postgres_sessions.begin() as db:
        valid = Finding(
            organization_id=organization_id,
            aws_account_id=account_id,
            asset_id=asset_id,
            rule_key="VALID_SUPPRESSION",
            rule_version=1,
            severity=FindingSeverity.MEDIUM,
            category="integrity",
            status=FindingStatus.SUPPRESSED,
            evidence_json={},
            first_seen_at=now,
            last_seen_at=now,
            suppressed_at=now,
            suppression_reason="Approved exception",
            suppressed_by_user_id=owner_id,
            last_evaluation_id=job_id,
        )
        db.add(valid)
        db.flush()


def test_stage4_suppression_and_terminal_races_are_serialized(
    postgres_sessions: sessionmaker[Session],
) -> None:
    with postgres_sessions() as db:
        owner, organization, account, asset = _stage4_account(db, "lifecycle-race")
        db.commit()
        first = EvaluationService(db).start(account.id, owner)
        finding = db.scalar(
            select(Finding).where(
                Finding.asset_id == asset.id,
                Finding.rule_key == "EC2_SG_SSH_OPEN_TO_WORLD",
            )
        )
        assert finding is not None
        running = EvaluationJob(
            organization_id=organization.id,
            aws_account_id=account.id,
            sequence=first.sequence + 1,
            status=EvaluationJobStatus.RUNNING,
            started_by_user_id=owner.id,
            started_at=now_utc(),
        )
        db.add(running)
        db.commit()
        ids = owner.id, organization.id, account.id, asset.id, finding.id, running.id

    owner_id, organization_id, _account_id, asset_id, finding_id, running_id = ids
    barrier = Barrier(2)

    def suppress() -> None:
        with postgres_sessions() as db:
            owner = db.get(User, owner_id)
            assert owner is not None
            barrier.wait()
            EvaluationService(db).suppress(
                organization_id,
                finding_id,
                owner,
                "Approved concurrent maintenance",
                now_utc() + timedelta(hours=1),
            )

    def resolve() -> None:
        with postgres_sessions.begin() as db:
            owner = db.get(User, owner_id)
            job = db.get(EvaluationJob, running_id)
            item = db.get(Asset, asset_id)
            assert owner is not None and job is not None and item is not None
            rule = default_registry.get("EC2_SG_SSH_OPEN_TO_WORLD")
            assert rule is not None
            item.metadata_json = {"ip_permissions": []}
            result = rule.evaluate(item, RuleContext((item,), evaluated_at=now_utc()))
            barrier.wait()
            EvaluationService(db)._apply_result(job, rule, item, result)

    results = _run_concurrently(suppress, resolve)
    assert all(result is None for result in results)
    with postgres_sessions() as db:
        finding = db.get(Finding, finding_id)
        assert finding is not None
        assert finding.status == FindingStatus.SUPPRESSED
        assert finding.suppression_reason == "Approved concurrent maintenance"
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.resource_id == finding_id,
                    AuditEvent.event_type == "security.finding.suppressed",
                )
            )
            == 1
        )

    terminal_barrier = Barrier(2)

    def finish(status: EvaluationJobStatus) -> EvaluationJob:
        with postgres_sessions() as db:
            owner = db.get(User, owner_id)
            assert owner is not None
            terminal_barrier.wait()
            return EvaluationService(db)._finish(running_id, owner, status, [])

    terminal = _run_concurrently(
        lambda: finish(EvaluationJobStatus.COMPLETED),
        lambda: finish(EvaluationJobStatus.FAILED),
    )
    assert sum(isinstance(result, EvaluationJob) for result in terminal) == 1
    assert sum(isinstance(result, AppError) for result in terminal) == 1
    with postgres_sessions() as db:
        job = db.get(EvaluationJob, running_id)
        assert job is not None
        assert job.status in {EvaluationJobStatus.COMPLETED, EvaluationJobStatus.FAILED}
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.resource_id == running_id,
                    AuditEvent.event_type.in_(
                        ["security.evaluation.completed", "security.evaluation.failed"]
                    ),
                )
            )
            == 1
        )


def test_stage4_actual_service_path_serializes_same_finding_creation(
    postgres_sessions: sessionmaker[Session],
) -> None:
    with postgres_sessions.begin() as db:
        owner, organization, account, asset = _stage4_account(db, "finding-service-race")
        at = now_utc()
        jobs = [
            EvaluationJob(
                organization_id=organization.id,
                aws_account_id=account.id,
                sequence=1,
                status=EvaluationJobStatus.COMPLETED,
                started_by_user_id=owner.id,
                started_at=at,
                finished_at=at,
            ),
            EvaluationJob(
                organization_id=organization.id,
                aws_account_id=account.id,
                sequence=2,
                status=EvaluationJobStatus.RUNNING,
                started_by_user_id=owner.id,
                started_at=at,
            ),
        ]
        db.add_all(jobs)
        db.flush()
        ids = account.id, asset.id, jobs[0].id, jobs[1].id

    account_id, asset_id, first_job_id, second_job_id = ids
    barrier = Barrier(2)

    def apply(job_id: uuid.UUID) -> None:
        with postgres_sessions.begin() as db:
            job = db.get(EvaluationJob, job_id)
            item = db.get(Asset, asset_id)
            rule = default_registry.get("EC2_SG_SSH_OPEN_TO_WORLD")
            assert job is not None and item is not None and rule is not None
            result = rule.evaluate(item, RuleContext((item,), evaluated_at=now_utc()))
            barrier.wait()
            EvaluationService(db)._apply_result(job, rule, item, result)

    results = _run_concurrently(
        lambda: apply(first_job_id),
        lambda: apply(second_job_id),
    )
    assert all(result is None for result in results)
    with postgres_sessions() as db:
        findings = db.scalars(
            select(Finding).where(
                Finding.aws_account_id == account_id,
                Finding.asset_id == asset_id,
                Finding.rule_key == "EC2_SG_SSH_OPEN_TO_WORLD",
            )
        ).all()
        assert len(findings) == 1
        assert findings[0].first_seen_at <= findings[0].last_seen_at
        persisted_jobs = db.scalars(
            select(EvaluationJob).where(EvaluationJob.id.in_([first_job_id, second_job_id]))
        ).all()
        assert sum(job.findings_created for job in persisted_jobs) == 1
        assert sum(job.findings_updated for job in persisted_jobs) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.resource_id == findings[0].id,
                    AuditEvent.event_type.in_(
                        ["security.finding.created", "security.finding.updated"]
                    ),
                )
            )
            == 2
        )


def test_concurrent_sandbox_approval_serializes_to_one_audited_transition(
    postgres_sessions: sessionmaker[Session],
) -> None:
    with postgres_sessions.begin() as db:
        owner = _user(f"remediation-admin-{uuid.uuid4()}@example.com")
        db.add(owner)
        db.flush()
        organization = Organization(
            name="Remediation administration concurrency",
            slug=f"remediation-admin-{uuid.uuid4()}",
            created_by_user_id=owner.id,
        )
        db.add(organization)
        db.flush()
        db.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=owner.id,
                role=OrganizationRole.OWNER,
                status=MembershipStatus.ACTIVE,
                joined_at=now_utc(),
            )
        )
        aws_account_id = str(uuid.uuid4().int % 1_000_000_000_000).zfill(12)
        account = AWSAccount(
            organization_id=organization.id,
            name="Remediation sandbox",
            account_id=aws_account_id,
            role_arn=None,
            external_id=f"cloudops-{uuid.uuid4()}",
            remediation_role_arn=(
                f"arn:aws:iam::{aws_account_id}:role/CloudOpsSandboxRemediationRole"
            ),
            remediation_external_id=f"cloudops-remediation-{uuid.uuid4()}",
            status=AWSAccountStatus.CONNECTED,
            connection_status=AWSAccountStatus.CONNECTED,
            created_by_user_id=owner.id,
        )
        db.add(account)
        db.flush()
        ids = owner.id, account.id

    owner_id, account_id = ids

    def approve(reason: str) -> AWSAccount:
        with postgres_sessions() as db:
            owner = db.get(User, owner_id)
            assert owner is not None
            return RemediationAdminService(db).grant_sandbox_approval(
                account_id, owner, reason
            )

    results = _run_concurrently(
        lambda: approve("Concurrent approval A"),
        lambda: approve("Concurrent approval B"),
    )
    assert sum(isinstance(result, AWSAccount) for result in results) == 1
    assert sum(
        isinstance(result, ConflictError)
        and result.code == "sandbox_already_approved"
        for result in results
    ) == 1
    with postgres_sessions() as db:
        persisted_account = db.get(AWSAccount, account_id)
        assert persisted_account is not None
        assert persisted_account.sandbox_approved is True
        assert persisted_account.sandbox_approved_at is not None
        assert persisted_account.sandbox_approved_by_user_id == owner_id
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.resource_id == account_id,
                    AuditEvent.event_type == "aws.account.sandbox_approved",
                )
            )
            == 1
        )
