from __future__ import annotations

import re
import secrets
import uuid
from collections.abc import Callable
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.exceptions.errors import AppError, ConflictError, NotFoundError
from app.models import AWSAccount, AWSExternalIDReservation, OrganizationMembership, User
from app.models.enums import AuditResult, AWSAccountStatus
from app.repositories.data import Repository
from app.security.rbac import Capability, role_has_capability
from app.services.aws_credentials import AWSConnectionFailure, TenantRoleCredentialProvider
from app.services.common import now_utc, record_audit
from app.services.organizations import OrganizationService

ACCOUNT_ID_PATTERN = re.compile(r"^[0-9]{12}$")
ROLE_ARN_PATTERN = re.compile(
    r"^arn:(aws|aws-us-gov|aws-cn):iam::(?P<account_id>[0-9]{12}):role/(?P<role>[A-Za-z0-9+=,.@_/-]{1,512})$"
)
PRINCIPAL_ARN_PATTERN = re.compile(
    r"^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:(root|role/[A-Za-z0-9+=,.@_/-]+|user/[A-Za-z0-9+=,.@_/-]+)$"
)


class AWSOnboardingService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        sts_client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.repo = Repository(db)
        self.sts_client_factory = sts_client_factory or boto3.client

    @staticmethod
    def generate_external_id() -> str:
        return f"cloudops-{secrets.token_urlsafe(32)}"

    @staticmethod
    def validate_account_id(account_id: str) -> str:
        value = account_id.strip()
        if not ACCOUNT_ID_PATTERN.fullmatch(value):
            raise AppError(
                "invalid_aws_account_id",
                "AWS account ID must contain exactly 12 digits.",
                422,
            )
        return value

    @staticmethod
    def validate_role_arn(role_arn: str, expected_account_id: str | None = None) -> str:
        value = role_arn.strip()
        match = ROLE_ARN_PATTERN.fullmatch(value)
        if not match:
            raise AppError("invalid_role_arn", "AWS role ARN is invalid.", 422)
        if expected_account_id is not None and match.group("account_id") != expected_account_id:
            raise AppError(
                "role_account_mismatch",
                "AWS role ARN must belong to the configured AWS account.",
                422,
            )
        return value

    def _require_account(
        self,
        account_id: uuid.UUID,
        actor: User,
        capability: Capability = Capability.AWS_ACCOUNTS_MANAGE,
        *,
        for_update: bool = False,
    ) -> tuple[AWSAccount, OrganizationMembership]:
        result = (
            self.repo.aws_account_for_user_for_update(account_id, actor.id)
            if for_update
            else self.repo.aws_account_for_user(account_id, actor.id)
        )
        if result is None:
            raise NotFoundError("aws_account_not_found", "AWS account was not found.")
        account, membership = result
        if not role_has_capability(membership.role, capability):
            from app.exceptions.errors import ForbiddenError

            raise ForbiddenError()
        return account, membership

    def _new_external_id(self) -> str:
        for _ in range(5):
            candidate = self.generate_external_id()
            if self.repo.external_id_reservation(candidate) is None:
                return candidate
        raise AppError(
            "external_id_generation_failed",
            "A unique AWS external ID could not be generated.",
            500,
        )

    def _reserve_external_id(self, organization_id: uuid.UUID) -> AWSExternalIDReservation:
        """Reserve an external ID durably, retrying database uniqueness collisions."""
        for _ in range(10):
            reservation = AWSExternalIDReservation(
                external_id=self.generate_external_id(),
                organization_id=organization_id,
            )
            try:
                with self.db.begin_nested():
                    self.db.add(reservation)
                    self.db.flush()
                return reservation
            except IntegrityError:
                continue
        raise AppError(
            "external_id_generation_failed",
            "A unique AWS external ID could not be generated.",
            500,
        )

    def create_account(
        self, organization_id: uuid.UUID, actor: User, name: str, account_id: str
    ) -> AWSAccount:
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.AWS_ACCOUNTS_MANAGE
        )
        # Account creation always returns onboarding trust policy details.
        # Validate the service principal before reserving an external ID or
        # committing anything, so a 503 cannot leave a hidden account behind.
        self._trusted_principals()
        provider_account_id = self.validate_account_id(account_id)
        if self.repo.aws_account_by_provider_id(organization_id, provider_account_id):
            raise ConflictError(
                "aws_account_exists", "This AWS account is already registered to the organization."
            )
        reservation = self._reserve_external_id(organization_id)
        account = AWSAccount(
            organization_id=organization_id,
            name=" ".join(name.split()),
            account_id=provider_account_id,
            external_id=reservation.external_id,
            created_by_user_id=actor.id,
        )
        self.db.add(account)
        self.db.flush()
        reservation.aws_account_id = account.id
        self._audit("aws.account.created", account, actor.id)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "aws_account_conflict", "The AWS account could not be registered."
            ) from exc
        self.db.refresh(account)
        return account

    def update_role(self, account_id: uuid.UUID, actor: User, role_arn: str) -> AWSAccount:
        account, _ = self._require_account(account_id, actor, for_update=True)
        value = self.validate_role_arn(role_arn, account.account_id)
        if self.repo.aws_account_by_role_arn(account.organization_id, value, account.id):
            raise ConflictError(
                "role_arn_exists", "This role ARN is already registered to the organization."
            )
        account.role_arn = value
        account.status = AWSAccountStatus.PENDING
        account.connection_status = AWSAccountStatus.PENDING
        account.failure_reason = None
        account.last_validated_at = None
        self._supersede_validation(account)
        self._audit("aws.account.updated", account, actor.id)
        self._commit_account(account)
        return account

    def update_account(
        self,
        account_id: uuid.UUID,
        actor: User,
        *,
        name: str | None,
        role_arn: str | None,
    ) -> AWSAccount:
        account, _ = self._require_account(account_id, actor, for_update=True)
        if name is not None:
            account.name = " ".join(name.split())
        if role_arn is not None:
            value = self.validate_role_arn(role_arn, account.account_id)
            if self.repo.aws_account_by_role_arn(account.organization_id, value, account.id):
                raise ConflictError(
                    "role_arn_exists", "This role ARN is already registered to the organization."
                )
            account.role_arn = value
            account.status = AWSAccountStatus.PENDING
            account.connection_status = AWSAccountStatus.PENDING
            account.failure_reason = None
            account.last_validated_at = None
            self._supersede_validation(account)
        elif name is not None:
            self._supersede_validation(account)
        self._audit("aws.account.updated", account, actor.id)
        self._commit_account(account)
        return account

    def list_accounts(self, organization_id: uuid.UUID, actor: User) -> list[AWSAccount]:
        OrganizationService(self.db).require_capability(
            organization_id, actor.id, Capability.AWS_ACCOUNTS_READ
        )
        return self.repo.aws_accounts(organization_id)

    def get_account(self, account_id: uuid.UUID, actor: User) -> AWSAccount:
        account, _ = self._require_account(account_id, actor, Capability.AWS_ACCOUNTS_READ)
        return account

    def get_onboarding_account(self, account_id: uuid.UUID, actor: User) -> AWSAccount:
        account, _ = self._require_account(account_id, actor, Capability.AWS_ACCOUNTS_MANAGE)
        self._audit("aws.account.onboarding_material_accessed", account, actor.id)
        self.db.commit()
        return account

    def assume_role(self, account: AWSAccount) -> str:
        return TenantRoleCredentialProvider(
            account,
            self.settings,
            sts_client_factory=self.sts_client_factory,
        ).validate_account()

    def assume_role_credentials(self, account: AWSAccount) -> dict[str, str]:
        """Legacy validation helper; discovery uses TenantRoleCredentialProvider."""
        if account.role_arn is None:
            raise AWSConnectionFailure("role_arn_missing")
        try:
            sts = self.sts_client_factory("sts", config=self.settings.aws_client_config)
            response = sts.assume_role(
                RoleArn=account.role_arn,
                RoleSessionName=self.settings.aws_role_session_name,
                ExternalId=account.external_id,
                DurationSeconds=900,
            )
            credentials = response["Credentials"]
            return {
                "AccessKeyId": str(credentials["AccessKeyId"]),
                "SecretAccessKey": str(credentials["SecretAccessKey"]),
                "SessionToken": str(credentials["SessionToken"]),
            }
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", "client_error"))
            safe_code = re.sub(r"[^a-z0-9]+", "_", code.casefold()).strip("_")
            raise AWSConnectionFailure(f"sts_{safe_code or 'client_error'}") from None
        except (BotoCoreError, KeyError, TypeError):
            raise AWSConnectionFailure("sts_validation_failed") from None

    def validate_connection(self, account_id: uuid.UUID, actor: User) -> AWSAccount:
        account, _ = self._require_account(account_id, actor, for_update=True)
        if account.role_arn is None:
            raise ConflictError("role_arn_required", "Add the AWS role ARN before validation.")
        if account.validation_token is not None:
            raise ConflictError(
                "validation_already_running",
                "Connection validation is already running for this AWS account.",
            )
        validation_token = uuid.uuid4()
        account.validation_token = validation_token
        account.validation_started_at = now_utc()
        account.lifecycle_version += 1
        self._audit("aws.account.validation_started", account, actor.id)
        self.db.commit()
        try:
            returned_account = self.assume_role(account)
            if returned_account != account.account_id:
                raise AWSConnectionFailure("caller_account_mismatch")
        except AWSConnectionFailure as exc:
            account = self._finish_validation(account_id, actor, validation_token)
            account.status = account.connection_status = AWSAccountStatus.FAILED
            account.failure_reason, account.last_validated_at = exc.reason, now_utc()
            self._audit(
                "aws.account.validation_failed",
                account,
                actor.id,
                result=AuditResult.FAILED,
                extra={"failure_reason": exc.reason},
            )
            self._commit_account(account)
            return account
        account = self._finish_validation(account_id, actor, validation_token)
        account.status = account.connection_status = AWSAccountStatus.CONNECTED
        account.failure_reason, account.last_validated_at = None, now_utc()
        self._audit("aws.account.validation_succeeded", account, actor.id)
        self._commit_account(account)
        return account

    def disconnect_account(self, account_id: uuid.UUID, actor: User) -> AWSAccount:
        account, _ = self._require_account(account_id, actor, for_update=True)
        if account.connection_status == AWSAccountStatus.DISCONNECTED:
            self.db.commit()
            self.db.refresh(account)
            return account
        account.status = AWSAccountStatus.DISCONNECTED
        account.connection_status = AWSAccountStatus.DISCONNECTED
        account.failure_reason = None
        self._supersede_validation(account)
        self._audit("aws.account.disconnected", account, actor.id)
        self._commit_account(account)
        return account

    def delete_account(self, account_id: uuid.UUID, actor: User) -> None:
        account, _ = self._require_account(account_id, actor, for_update=True)
        reservation = self.repo.external_id_reservation_for_account(account.id)
        if reservation is None:
            raise AppError(
                "external_id_reservation_missing",
                "The AWS account external ID reservation is missing.",
                500,
            )
        reservation.aws_account_id = None
        reservation.retired_at = now_utc()
        self._supersede_validation(account)
        self._audit("aws.account.deleted", account, actor.id)
        self.db.delete(account)
        self.db.commit()

    def trust_policy(self, account: AWSAccount) -> dict[str, Any]:
        principals = self._trusted_principals()
        principal: str | list[str] = principals[0] if len(principals) == 1 else principals
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": principal},
                    "Action": "sts:AssumeRole",
                    "Condition": {"StringEquals": {"sts:ExternalId": account.external_id}},
                }
            ],
        }

    def _trusted_principals(self) -> list[str]:
        configured = [
            principal.strip()
            for principal in self.settings.aws_trusted_principal_arns.split(",")
            if principal.strip()
        ]
        if not configured and self.settings.aws_trusted_principal_arn.strip():
            configured = [self.settings.aws_trusted_principal_arn.strip()]
        principals = list(dict.fromkeys(configured))
        if (
            not principals
            or len(principals) > 4
            or any(not PRINCIPAL_ARN_PATTERN.fullmatch(principal) for principal in principals)
        ):
            raise AppError(
                "aws_principal_not_configured",
                "CloudOps AWS trusted principals are not configured.",
                503,
            )
        return principals

    @staticmethod
    def permission_policy() -> dict[str, str]:
        return {
            "policy_name": "SecurityAudit",
            "managed_policy_arn": "arn:aws:iam::aws:policy/SecurityAudit",
            "description": "Attach the AWS managed SecurityAudit policy to CloudOpsReadOnlyRole.",
        }

    @staticmethod
    def onboarding_instructions() -> list[str]:
        return [
            "Create an IAM role named CloudOpsReadOnlyRole in the target AWS account.",
            "Apply the displayed trust policy exactly, including the generated external ID.",
            "Attach the AWS managed SecurityAudit policy.",
            "Copy the role ARN into CloudOps and validate the connection.",
            "CloudOps will call STS AssumeRole and GetCallerIdentity only during "
            "Stage 2 validation.",
        ]

    def _commit_account(self, account: AWSAccount) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "aws_account_conflict", "The AWS account update conflicts with another record."
            ) from exc
        self.db.refresh(account)

    def _finish_validation(
        self, account_id: uuid.UUID, actor: User, validation_token: uuid.UUID
    ) -> AWSAccount:
        account, _ = self._require_account(account_id, actor, for_update=True)
        if account.validation_token != validation_token:
            self.db.rollback()
            raise ConflictError(
                "validation_superseded",
                "Connection validation was superseded by a newer account change.",
            )
        account.validation_token = None
        account.validation_started_at = None
        account.lifecycle_version += 1
        return account

    @staticmethod
    def _supersede_validation(account: AWSAccount) -> None:
        account.validation_token = None
        account.validation_started_at = None
        account.lifecycle_version += 1

    def _audit(
        self,
        event_type: str,
        account: AWSAccount,
        actor_user_id: uuid.UUID,
        *,
        result: AuditResult = AuditResult.SUCCEEDED,
        extra: dict[str, Any] | None = None,
    ) -> None:
        metadata: dict[str, Any] = {
            "aws_account_id": account.account_id,
            "role_arn": account.role_arn,
        }
        if extra:
            metadata.update(extra)
        record_audit(
            self.db,
            event_type,
            "aws_account",
            organization_id=account.organization_id,
            actor_user_id=actor_user_id,
            resource_id=account.id,
            result=result,
            metadata=metadata,
        )
