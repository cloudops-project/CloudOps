from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.exceptions.errors import AuthenticationError, ConflictError
from app.models import Organization, OrganizationMembership, RefreshTokenSession, User
from app.models.enums import AuditResult, MembershipStatus, OrganizationRole, UserStatus
from app.repositories.data import Repository
from app.security.passwords import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    validate_password,
    verify_password,
)
from app.security.tokens import create_access_token, generate_opaque_token, hash_opaque_token
from app.services.common import normalize_email, now_utc, record_audit, slugify


@dataclass
class IssuedTokens:
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.repo = Repository(db)

    def register(
        self, email: str, password: str, full_name: str, organization_name: str | None
    ) -> User:
        normalized = normalize_email(email)
        validate_password(password, normalized)
        if self.repo.user_by_email(normalized):
            raise ConflictError("email_in_use", "An account with this email already exists.")
        user = User(
            email=email.strip(),
            normalized_email=normalized,
            password_hash=hash_password(password),
            full_name=full_name,
            status=UserStatus.ACTIVE,
        )
        self.db.add(user)
        self.db.flush()
        record_audit(self.db, "user.registered", "user", actor_user_id=user.id, resource_id=user.id)
        if organization_name:
            slug = self._available_slug(slugify(organization_name))
            organization = Organization(
                name=organization_name, slug=slug, created_by_user_id=user.id
            )
            self.db.add(organization)
            self.db.flush()
            self.db.add(
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=user.id,
                    role=OrganizationRole.OWNER,
                    status=MembershipStatus.ACTIVE,
                    joined_at=now_utc(),
                )
            )
            record_audit(
                self.db,
                "organization.created",
                "organization",
                organization_id=organization.id,
                actor_user_id=user.id,
                resource_id=organization.id,
            )
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("registration_conflict", "Unable to create this account.") from exc
        self.db.refresh(user)
        return user

    def _available_slug(self, base: str) -> str:
        if not base:
            base = "organization"
        candidate = base
        counter = 2
        while self.repo.organization_by_slug(candidate):
            suffix = f"-{counter}"
            candidate = f"{base[: 100 - len(suffix)]}{suffix}"
            counter += 1
        return candidate

    def login(
        self, email: str, password: str, user_agent: str | None, ip: str | None
    ) -> IssuedTokens:
        user = self.repo.user_by_email(normalize_email(email))
        valid = verify_password(password, user.password_hash if user else DUMMY_PASSWORD_HASH)
        if not user or not valid or user.status != UserStatus.ACTIVE:
            record_audit(
                self.db,
                "auth.login_failed",
                "user",
                result=AuditResult.FAILED,
                actor_user_id=user.id if user else None,
                metadata={
                    "email_fingerprint": hashlib.sha256(
                        normalize_email(email).encode()
                    ).hexdigest()[:12]
                },
                ip_address=ip,
                user_agent=user_agent,
            )
            self.db.commit()
            raise AuthenticationError("invalid_credentials", "Invalid email or password.")
        user.last_login_at = now_utc()
        tokens = self._issue(user.id, user_agent, ip)
        record_audit(
            self.db,
            "auth.login_succeeded",
            "user",
            actor_user_id=user.id,
            resource_id=user.id,
            ip_address=ip,
            user_agent=user_agent,
        )
        self.db.commit()
        return tokens

    def _issue(
        self,
        user_id: uuid.UUID,
        user_agent: str | None,
        ip: str | None,
        family_id: uuid.UUID | None = None,
    ) -> IssuedTokens:
        raw = generate_opaque_token()
        now = now_utc()
        self.db.add(
            RefreshTokenSession(
                user_id=user_id,
                token_hash=hash_opaque_token(raw),
                family_id=family_id or uuid.uuid4(),
                issued_at=now,
                expires_at=now + timedelta(days=self.settings.refresh_token_expire_days),
                user_agent=user_agent,
                ip_address=ip,
            )
        )
        return IssuedTokens(create_access_token(user_id, self.settings), raw)

    def refresh(self, raw: str, user_agent: str | None, ip: str | None) -> IssuedTokens:
        # The row lock is held by this session's transaction through replacement creation,
        # revocation, audit recording, and commit. This prevents two rotations succeeding.
        session = self.repo.refresh_session_for_update(hash_opaque_token(raw))
        if not session:
            raise AuthenticationError("invalid_refresh_token", "Refresh token is invalid.")
        if session.revoked_at is not None:
            self.repo.revoke_family(session.family_id, now_utc())
            record_audit(
                self.db,
                "auth.refresh_reuse_detected",
                "refresh_session",
                result=AuditResult.FAILED,
                actor_user_id=session.user_id,
                resource_id=session.id,
                ip_address=ip,
                user_agent=user_agent,
            )
            self.db.commit()
            raise AuthenticationError("refresh_token_reused", "Refresh token is no longer valid.")
        from app.services.common import is_expired

        if is_expired(session.expires_at):
            session.revoked_at = now_utc()
            self.db.commit()
            raise AuthenticationError("refresh_token_expired", "Refresh token has expired.")
        user = self.repo.user(session.user_id)
        if not user or user.status != UserStatus.ACTIVE:
            raise AuthenticationError()
        new_tokens = self._issue(user.id, user_agent, ip, session.family_id)
        self.db.flush()
        replacement = self.repo.refresh_session(hash_opaque_token(new_tokens.refresh_token))
        session.revoked_at = now_utc()
        session.replaced_by_id = replacement.id if replacement else None
        record_audit(
            self.db,
            "auth.token_refreshed",
            "refresh_session",
            actor_user_id=user.id,
            resource_id=session.id,
            ip_address=ip,
            user_agent=user_agent,
        )
        self.db.commit()
        return new_tokens

    def logout(
        self, raw: str | None, user_id: uuid.UUID | None, user_agent: str | None, ip: str | None
    ) -> None:
        session = self.repo.refresh_session(hash_opaque_token(raw)) if raw else None
        if session and session.revoked_at is None:
            session.revoked_at = now_utc()
        actor_user_id = session.user_id if session is not None else user_id
        record_audit(
            self.db,
            "auth.logged_out",
            "refresh_session",
            actor_user_id=actor_user_id,
            resource_id=session.id if session else None,
            ip_address=ip,
            user_agent=user_agent,
        )
        self.db.commit()

    def change_password(self, user: User, current: str, new: str) -> None:
        if not verify_password(current, user.password_hash):
            raise AuthenticationError("invalid_current_password", "Current password is incorrect.")
        validate_password(new, user.normalized_email)
        user.password_hash = hash_password(new)
        from sqlalchemy import update

        self.db.execute(
            update(RefreshTokenSession)
            .where(
                RefreshTokenSession.user_id == user.id,
                RefreshTokenSession.revoked_at.is_(None),
            )
            .values(revoked_at=now_utc())
        )
        self.db.commit()
