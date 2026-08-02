from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exceptions.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.models import Asset, AWSAccount, Finding, RemediationRequest, User
from app.models.enums import (
    AWSAccountStatus,
    FindingStatus,
    RemediationExecutionMode,
    RemediationStatus,
)
from app.repositories.data import Repository
from app.schemas.aws_account import REMEDIATION_ROLE_ARN_PATTERN
from app.security.rbac import Capability, role_has_capability
from app.services.ai_safety import canonical_json
from app.services.common import now_utc, record_audit
from app.services.organizations import OrganizationService
from app.services.remediation_actions import default_remediation_actions

LIVE_ACTIONS = frozenset(
    {
        "s3.enable_public_access_block",
        "ec2.revoke_approved_public_ingress",
    }
)


class RemediationAdminService:
    """Owner-only, tenant-scoped administration for future live remediation.

    This service only changes PostgreSQL state. It never constructs an AWS
    client, assumes a role, enqueues a job, or enables an operator feature flag.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = Repository(db)

    @staticmethod
    def generate_external_id() -> str:
        return f"cloudops-remediation-{secrets.token_urlsafe(32)}"

    @staticmethod
    def masked_role_arn(role_arn: str | None) -> str | None:
        if role_arn is None:
            return None
        match = re.fullmatch(
            r"(?P<prefix>arn:(?:aws|aws-us-gov|aws-cn):iam::)(?P<account>[0-9]{12})"
            r"(?P<suffix>:role/[A-Za-z0-9+=,.@_/-]{1,512})",
            role_arn,
        )
        if match is None:
            return None
        return (
            f"{match.group('prefix')}********{match.group('account')[-4:]}"
            f"{match.group('suffix')}"
        )

    def _require_account(
        self, account_id: uuid.UUID, actor: User, *, for_update: bool = True
    ) -> AWSAccount:
        result = (
            self.repo.aws_account_for_user_for_update(account_id, actor.id)
            if for_update
            else self.repo.aws_account_for_user(account_id, actor.id)
        )
        if result is None:
            raise NotFoundError("aws_account_not_found", "AWS account was not found.")
        account, membership = result
        if not role_has_capability(membership.role, Capability.REMEDIATION_ADMIN):
            raise ForbiddenError(
                "remediation_admin_forbidden",
                "Only an organization owner can administer remediation trust.",
            )
        return account

    def get_status(self, account_id: uuid.UUID, actor: User) -> AWSAccount:
        return self._require_account(account_id, actor, for_update=False)

    def _new_external_id(self) -> str:
        for _ in range(10):
            candidate = self.generate_external_id()
            exists = self.db.scalar(
                select(AWSAccount.id).where(
                    or_(
                        AWSAccount.external_id == candidate,
                        AWSAccount.remediation_external_id == candidate,
                    )
                )
            )
            if exists is None:
                return candidate
        raise AppError(
            "external_id_generation_failed",
            "A unique remediation External ID could not be generated.",
            500,
        )

    @staticmethod
    def _revoke_approval(account: AWSAccount) -> None:
        account.sandbox_approved = False
        account.sandbox_approved_at = None
        account.sandbox_approved_by_user_id = None

    def _audit(
        self,
        event_type: str,
        account: AWSAccount,
        actor: User,
        *,
        reason: str | None = None,
    ) -> None:
        metadata: dict[str, Any] = {
            "aws_account_id": account.account_id,
            "remediation_trust_configured": bool(
                account.remediation_role_arn and account.remediation_external_id
            ),
            "sandbox_approved": account.sandbox_approved,
            "occurred_at": now_utc().isoformat(),
        }
        if reason is not None:
            metadata["reason"] = " ".join(reason.split())[:500]
        record_audit(
            self.db,
            event_type,
            "aws_account",
            organization_id=account.organization_id,
            actor_user_id=actor.id,
            resource_id=account.id,
            metadata=metadata,
        )

    def _commit(self, account: AWSAccount) -> AWSAccount:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "remediation_admin_conflict",
                "The remediation administration state changed concurrently.",
            ) from exc
        self.db.refresh(account)
        return account

    def configure_trust(
        self, account_id: uuid.UUID, actor: User, remediation_role_arn: str
    ) -> tuple[AWSAccount, str | None]:
        account = self._require_account(account_id, actor)
        value = remediation_role_arn.strip()
        match = REMEDIATION_ROLE_ARN_PATTERN.fullmatch(value)
        if match is None:
            raise AppError(
                "remediation_role_invalid", "The remediation role ARN is invalid.", 422
            )
        if match.group("account_id") != account.account_id:
            raise AppError(
                "remediation_role_account_mismatch",
                "The remediation role ARN belongs to a different AWS account.",
                422,
            )
        if (
            account.remediation_role_arn == value
            and account.remediation_external_id
        ):
            self.db.commit()
            self.db.refresh(account)
            return account, None
        external_id = self._new_external_id()
        account.remediation_role_arn = value
        account.remediation_external_id = external_id
        self._revoke_approval(account)
        self._audit("aws.account.remediation_trust_configured", account, actor)
        return self._commit(account), external_id

    def rotate_external_id(
        self, account_id: uuid.UUID, actor: User, reason: str
    ) -> tuple[AWSAccount, str]:
        account = self._require_account(account_id, actor)
        if not account.remediation_role_arn or not account.remediation_external_id:
            raise ConflictError(
                "remediation_trust_not_configured",
                "Remediation trust must be configured before rotation.",
            )
        external_id = self._new_external_id()
        account.remediation_external_id = external_id
        self._revoke_approval(account)
        self._audit("aws.account.remediation_external_id_rotated", account, actor, reason=reason)
        return self._commit(account), external_id

    def clear_trust(self, account_id: uuid.UUID, actor: User, reason: str) -> AWSAccount:
        account = self._require_account(account_id, actor)
        account.remediation_role_arn = None
        account.remediation_external_id = None
        self._revoke_approval(account)
        self._audit("aws.account.remediation_trust_cleared", account, actor, reason=reason)
        return self._commit(account)

    def grant_sandbox_approval(
        self, account_id: uuid.UUID, actor: User, reason: str
    ) -> AWSAccount:
        account = self._require_account(account_id, actor)
        if account.sandbox_approved:
            raise ConflictError("sandbox_already_approved", "The sandbox is already approved.")
        if not account.remediation_role_arn or not account.remediation_external_id:
            raise ConflictError(
                "sandbox_approval_prerequisite_missing",
                "Complete remediation trust before approving the sandbox.",
            )
        if account.connection_status != AWSAccountStatus.CONNECTED:
            raise ConflictError(
                "sandbox_approval_prerequisite_missing",
                "The read-only AWS account connection must be validated first.",
            )
        account.sandbox_approved = True
        account.sandbox_approved_at = now_utc()
        account.sandbox_approved_by_user_id = actor.id
        self._audit("aws.account.sandbox_approved", account, actor, reason=reason)
        return self._commit(account)

    def revoke_sandbox_approval(
        self, account_id: uuid.UUID, actor: User, reason: str
    ) -> AWSAccount:
        account = self._require_account(account_id, actor)
        if not account.sandbox_approved:
            raise ConflictError("sandbox_not_approved", "The sandbox is not approved.")
        self._revoke_approval(account)
        self._audit("aws.account.sandbox_approval_revoked", account, actor, reason=reason)
        return self._commit(account)

    def prepare_live_request(
        self, organization_id: uuid.UUID, request_id: uuid.UUID, actor: User
    ) -> RemediationRequest:
        membership = OrganizationService(self.db).require_member(organization_id, actor.id)
        if not role_has_capability(membership.role, Capability.REMEDIATION_ADMIN):
            raise ForbiddenError(
                "remediation_admin_forbidden",
                "Only an organization owner can prepare live remediation.",
            )
        request = self.db.scalar(
            select(RemediationRequest)
            .where(
                RemediationRequest.id == request_id,
                RemediationRequest.organization_id == organization_id,
            )
            .with_for_update()
        )
        if request is None:
            raise NotFoundError(
                "remediation_request_not_found", "Remediation request was not found."
            )
        if request.status != RemediationStatus.APPROVED:
            raise ConflictError(
                "live_request_not_eligible",
                "Only an approved remediation request can be prepared for live execution.",
            )
        calculated = hashlib.sha256(
            canonical_json(request.request_snapshot_json).encode()
        ).hexdigest()
        if (
            calculated != request.request_snapshot_hash
            or request.approved_snapshot_hash != calculated
        ):
            raise ConflictError(
                "live_request_not_eligible", "The approved remediation snapshot is stale."
            )
        if request.action_key not in LIVE_ACTIONS:
            raise ConflictError(
                "remediation_action_not_supported",
                "The remediation action is not supported for live execution.",
            )
        account = self.db.scalar(
            select(AWSAccount)
            .where(
                AWSAccount.id == request.aws_account_id,
                AWSAccount.organization_id == organization_id,
            )
            .with_for_update()
        )
        if account is None:
            raise NotFoundError("aws_account_not_found", "AWS account was not found.")
        if (
            not account.sandbox_approved
            or account.sandbox_approved_at is None
            or account.sandbox_approved_by_user_id is None
            or not account.remediation_role_arn
            or not account.remediation_external_id
        ):
            raise ConflictError(
                "live_request_not_eligible",
                "The AWS account is not approved for live sandbox remediation.",
            )
        finding = self.db.scalar(
            select(Finding).where(
                Finding.id == request.finding_id,
                Finding.aws_account_id == account.id,
                Finding.organization_id == organization_id,
            )
        )
        if finding is None or finding.status != FindingStatus.OPEN:
            raise ConflictError("live_request_not_eligible", "The finding is no longer open.")
        evidence_hash = hashlib.sha256(canonical_json(finding.evidence_json).encode()).hexdigest()
        if evidence_hash != request.request_snapshot_json.get("finding_evidence_hash"):
            raise ConflictError("live_request_not_eligible", "The finding evidence is stale.")
        action = default_remediation_actions.for_rule(finding.rule_key)
        if action is None or action.key != request.action_key:
            raise ConflictError(
                "remediation_action_not_supported",
                "The finding does not map to the approved live action.",
            )
        if finding.asset_id is None:
            raise ConflictError("live_request_not_eligible", "The finding has no target asset.")
        asset = self.db.scalar(
            select(Asset).where(
                Asset.id == finding.asset_id,
                Asset.aws_account_id == account.id,
                Asset.organization_id == organization_id,
            )
        )
        if asset is None or not asset.arn:
            raise ConflictError("live_request_not_eligible", "The target asset is unavailable.")
        snapshot = dict(request.request_snapshot_json)
        snapshot.update(
            {
                "execution_mode": RemediationExecutionMode.LIVE_AWS.value,
                "executor_key": "aws",
                "dry_run": False,
                "target_region": asset.region,
                "target_resource_arn": asset.arn,
                "asset_evidence_hash": hashlib.sha256(
                    canonical_json(asset.metadata_json).encode()
                ).hexdigest(),
            }
        )
        snapshot_hash = hashlib.sha256(canonical_json(snapshot).encode()).hexdigest()
        request.execution_mode = RemediationExecutionMode.LIVE_AWS
        request.executor_key = "aws"
        request.dry_run = False
        request.target_region = asset.region
        request.target_resource_arn = asset.arn
        request.request_snapshot_json = snapshot
        request.request_snapshot_hash = snapshot_hash
        request.idempotency_key = hashlib.sha256(
            f"{organization_id}:{finding.id}:{snapshot_hash}".encode()
        ).hexdigest()
        request.preview_json = {**request.preview_json, "dry_run": False}
        request.status = RemediationStatus.PENDING_APPROVAL
        request.approved_at = None
        request.approved_by_user_id = None
        request.approved_snapshot_hash = None
        record_audit(
            self.db,
            "remediation.request.live_prepared",
            "remediation_request",
            organization_id=organization_id,
            actor_user_id=actor.id,
            resource_id=request.id,
            metadata={"action_key": request.action_key, "aws_account_id": str(account.id)},
        )
        self.db.commit()
        self.db.refresh(request)
        return request
