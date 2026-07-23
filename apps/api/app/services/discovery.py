from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, ClassVar

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.exceptions.errors import ConflictError, NotFoundError
from app.models import Asset, AWSAccount, DiscoveryJob, User
from app.models.enums import AssetType, AuditResult, AWSAccountStatus, DiscoveryJobStatus
from app.repositories.assets import AssetRepository, DiscoveryJobRepository
from app.security.rbac import Capability
from app.services.aws_onboarding import AWSConnectionFailure, AWSOnboardingService
from app.services.common import now_utc, record_audit
from app.services.organizations import OrganizationService

ClientFactory = Callable[[str, str | None], Any]
SENSITIVE_KEYS = re.compile(
    r"(access.?key|secret|session.?token|credential|password|authorization)", re.I
)


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
            if not SENSITIVE_KEYS.search(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def tags_dict(tags: Iterable[dict[str, Any]] | None) -> dict[str, str]:
    return {
        str(tag.get("Key")): str(tag.get("Value", ""))
        for tag in (tags or [])
        if tag.get("Key") and not SENSITIVE_KEYS.search(str(tag.get("Key")))
    }


def iam_tags(client: Any, operation: str, argument: str, value: str) -> dict[str, str]:
    if hasattr(client, "can_paginate") and client.can_paginate(operation):
        pages = client.get_paginator(operation).paginate(**{argument: value})
        return tags_dict(tag for page in pages for tag in page.get("Tags", []))
    return tags_dict(getattr(client, operation)(**{argument: value}).get("Tags"))


@dataclass(frozen=True)
class NormalizedAsset:
    asset_type: AssetType
    resource_id: str
    arn: str | None
    name: str
    region: str
    status: str | None
    tags: dict[str, str]
    metadata: dict[str, Any]


class EC2DiscoveryService:
    asset_types: ClassVar[set[AssetType]] = {AssetType.EC2_INSTANCE}

    def discover(
        self, client_factory: ClientFactory, regions: list[str], account_id: str
    ) -> list[NormalizedAsset]:
        assets: list[NormalizedAsset] = []
        for region in regions:
            client = client_factory("ec2", region)
            for page in client.get_paginator("describe_instances").paginate():
                for reservation in page.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        instance_id = instance["InstanceId"]
                        tags = tags_dict(instance.get("Tags"))
                        assets.append(
                            NormalizedAsset(
                                AssetType.EC2_INSTANCE,
                                instance_id,
                                f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}",
                                tags.get("Name", instance_id),
                                region,
                                instance.get("State", {}).get("Name"),
                                tags,
                                json_safe(
                                    {
                                        "instance_type": instance.get("InstanceType"),
                                        "vpc_id": instance.get("VpcId"),
                                        "subnet_id": instance.get("SubnetId"),
                                        "security_group_ids": [
                                            group.get("GroupId")
                                            for group in instance.get("SecurityGroups", [])
                                        ],
                                        "launch_time": instance.get("LaunchTime"),
                                    }
                                ),
                            )
                        )
        return assets


class S3DiscoveryService:
    asset_types: ClassVar[set[AssetType]] = {AssetType.S3_BUCKET}

    def discover(
        self, client_factory: ClientFactory, regions: list[str], account_id: str
    ) -> list[NormalizedAsset]:
        del regions, account_id
        client = client_factory("s3", None)
        assets: list[NormalizedAsset] = []
        for page in client.get_paginator("list_buckets").paginate():
            for bucket in page.get("Buckets", []):
                name = bucket["Name"]
                location = (
                    client.get_bucket_location(Bucket=name).get("LocationConstraint") or "us-east-1"
                )
                try:
                    tags = tags_dict(client.get_bucket_tagging(Bucket=name).get("TagSet"))
                except ClientError as exc:
                    if exc.response.get("Error", {}).get("Code") not in {
                        "NoSuchTagSet",
                        "NoSuchTagSetError",
                    }:
                        raise
                    tags = {}
                assets.append(
                    NormalizedAsset(
                        AssetType.S3_BUCKET,
                        name,
                        f"arn:aws:s3:::{name}",
                        name,
                        location,
                        "available",
                        tags,
                        json_safe({"creation_date": bucket.get("CreationDate")}),
                    )
                )
        return assets


class IAMDiscoveryService:
    asset_types: ClassVar[set[AssetType]] = {
        AssetType.IAM_USER,
        AssetType.IAM_ROLE,
        AssetType.IAM_GROUP,
        AssetType.IAM_POLICY,
    }

    def discover(
        self, client_factory: ClientFactory, regions: list[str], account_id: str
    ) -> list[NormalizedAsset]:
        del regions, account_id
        client = client_factory("iam", None)
        assets: list[NormalizedAsset] = []
        seen: set[tuple[AssetType, str]] = set()
        specs = (
            ("list_users", "Users", AssetType.IAM_USER, "UserId", "UserName"),
            ("list_roles", "Roles", AssetType.IAM_ROLE, "RoleId", "RoleName"),
            ("list_groups", "Groups", AssetType.IAM_GROUP, "GroupId", "GroupName"),
            ("list_policies", "Policies", AssetType.IAM_POLICY, "PolicyId", "PolicyName"),
        )
        for operation, key, asset_type, id_key, name_key in specs:
            kwargs = {"Scope": "Local"} if operation == "list_policies" else {}
            for page in client.get_paginator(operation).paginate(**kwargs):
                for item in page.get(key, []):
                    identity = (asset_type, str(item[id_key]))
                    if identity in seen:
                        continue
                    seen.add(identity)
                    tag_method = {
                        AssetType.IAM_USER: "list_user_tags",
                        AssetType.IAM_ROLE: "list_role_tags",
                        AssetType.IAM_POLICY: "list_policy_tags",
                    }.get(asset_type)
                    tags: dict[str, str] = {}
                    if tag_method:
                        argument = {
                            AssetType.IAM_USER: "UserName",
                            AssetType.IAM_ROLE: "RoleName",
                            AssetType.IAM_POLICY: "PolicyArn",
                        }[asset_type]
                        value = (
                            item[name_key] if asset_type != AssetType.IAM_POLICY else item["Arn"]
                        )
                        tags = iam_tags(client, tag_method, argument, value)
                    metadata = {"path": item.get("Path"), "creation_date": item.get("CreateDate")}
                    if asset_type == AssetType.IAM_ROLE:
                        metadata["max_session_duration"] = item.get("MaxSessionDuration")
                    if asset_type == AssetType.IAM_POLICY:
                        metadata.update(
                            {
                                "attachment_count": item.get("AttachmentCount"),
                                "update_date": item.get("UpdateDate"),
                            }
                        )
                    assets.append(
                        NormalizedAsset(
                            asset_type,
                            str(item[id_key]),
                            item.get("Arn"),
                            str(item[name_key]),
                            "global",
                            "active",
                            tags,
                            json_safe(metadata),
                        )
                    )
        return assets


class RDSDiscoveryService:
    asset_types: ClassVar[set[AssetType]] = {AssetType.RDS_INSTANCE}

    def discover(
        self, client_factory: ClientFactory, regions: list[str], account_id: str
    ) -> list[NormalizedAsset]:
        del account_id
        assets: list[NormalizedAsset] = []
        for region in regions:
            client = client_factory("rds", region)
            for page in client.get_paginator("describe_db_instances").paginate():
                for item in page.get("DBInstances", []):
                    arn = item.get("DBInstanceArn")
                    tags = (
                        tags_dict(client.list_tags_for_resource(ResourceName=arn).get("TagList"))
                        if arn
                        else {}
                    )
                    vpc_id = (item.get("DBSubnetGroup") or {}).get("VpcId")
                    metadata = {
                        "engine": item.get("Engine"),
                        "engine_version": item.get("EngineVersion"),
                        "instance_class": item.get("DBInstanceClass"),
                        "endpoint": json_safe(item.get("Endpoint")),
                        "multi_az": item.get("MultiAZ"),
                        "vpc_id": vpc_id,
                    }
                    identifier = item["DBInstanceIdentifier"]
                    assets.append(
                        NormalizedAsset(
                            AssetType.RDS_INSTANCE,
                            identifier,
                            arn,
                            identifier,
                            region,
                            item.get("DBInstanceStatus"),
                            tags,
                            json_safe(metadata),
                        )
                    )
        return assets


def safe_aws_error(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", "client_error"))
        value = re.sub(r"[^a-z0-9]+", "_", code.casefold()).strip("_")
        return value[:80] or "client_error"
    if isinstance(exc, AWSConnectionFailure):
        return exc.reason[:80]
    if isinstance(exc, BotoCoreError):
        return "aws_service_error"
    return "discovery_service_failed"


class DiscoveryOrchestrator:
    services = (
        EC2DiscoveryService(),
        S3DiscoveryService(),
        IAMDiscoveryService(),
        RDSDiscoveryService(),
    )

    def __init__(
        self, db: Session, settings: Settings, client_factory: ClientFactory | None = None
    ) -> None:
        self.db, self.settings = db, settings
        self.assets, self.jobs = AssetRepository(db), DiscoveryJobRepository(db)
        self.client_factory = client_factory

    def start(self, account_id: uuid.UUID, actor: User) -> DiscoveryJob:
        account = self.db.scalar(
            select(AWSAccount).where(AWSAccount.id == account_id).with_for_update()
        )
        if not account:
            raise NotFoundError("aws_account_not_found", "AWS account was not found.")
        OrganizationService(self.db).require_capability(
            account.organization_id, actor.id, Capability.DISCOVERY_START
        )
        if account.connection_status != AWSAccountStatus.CONNECTED:
            raise ConflictError(
                "aws_account_not_connected", "Only connected AWS accounts can run discovery."
            )
        if self.jobs.active_for_account(account.id):
            raise ConflictError(
                "discovery_already_running", "A discovery job is already active for this account."
            )
        job = DiscoveryJob(
            organization_id=account.organization_id,
            aws_account_id=account.id,
            started_by_user_id=actor.id,
        )
        try:
            self.jobs.create(job)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "discovery_already_running", "A discovery job is already active for this account."
            ) from exc
        return self.run(job.id, actor)

    def run(self, job_id: uuid.UUID, actor: User) -> DiscoveryJob:
        job = self.db.scalar(
            select(DiscoveryJob)
            .where(DiscoveryJob.id == job_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if not job:
            raise NotFoundError("discovery_job_not_found", "Discovery job was not found.")
        if job.status != DiscoveryJobStatus.PENDING:
            raise ConflictError(
                "discovery_job_not_pending",
                "Only a pending discovery job can start execution.",
            )
        account = self.db.get(AWSAccount, job.aws_account_id)
        if not account:
            raise NotFoundError("aws_account_not_found", "AWS account was not found.")
        job.status, job.started_at = DiscoveryJobStatus.RUNNING, now_utc()
        record_audit(
            self.db,
            "aws.discovery.started",
            "discovery_job",
            organization_id=job.organization_id,
            actor_user_id=actor.id,
            resource_id=job.id,
            metadata={"aws_account_id": account.account_id, "job_id": str(job.id)},
        )
        self.db.commit()
        errors: dict[str, str] = {}
        service_results: dict[str, str] = {}
        successes = 0
        try:
            factory = self.client_factory or self._assumed_client_factory(account)
        except Exception as exc:
            failure = {"sts": safe_aws_error(exc)}
            return self._finish(
                job,
                actor,
                DiscoveryJobStatus.FAILED,
                failure,
                service_results=failure,
            )
        for service in self.services:
            name = service.__class__.__name__.replace("DiscoveryService", "").lower()
            try:
                normalized = service.discover(
                    factory, self.settings.discovery_regions, account.account_id
                )
                counts = self._upsert(account, normalized, service.asset_types)
                job.assets_discovered += len(normalized)
                job.assets_created += counts[0]
                job.assets_updated += counts[1]
                job.assets_deactivated += counts[2]
                self.db.commit()
                successes += 1
                service_results[name] = "succeeded"
            except Exception as exc:
                self.db.rollback()
                job = self.db.get(DiscoveryJob, job.id)
                assert job is not None
                errors[name] = safe_aws_error(exc)
                service_results[name] = errors[name]
        status = (
            DiscoveryJobStatus.COMPLETED
            if not errors
            else (
                DiscoveryJobStatus.PARTIALLY_COMPLETED if successes else DiscoveryJobStatus.FAILED
            )
        )
        return self._finish(job, actor, status, errors, service_results=service_results)

    def _assumed_client_factory(self, account: AWSAccount) -> ClientFactory:
        credentials = AWSOnboardingService(self.db, self.settings).assume_role_credentials(account)

        def factory(service: str, region: str | None) -> Any:
            return boto3.client(
                service,
                region_name=region,
                config=self.settings.aws_client_config,
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
            )

        return factory

    def _upsert(
        self, account: AWSAccount, discovered: list[NormalizedAsset], asset_types: set[AssetType]
    ) -> tuple[int, int, int]:
        # Account-level locking gives asset upsert/reactivation/deactivation one deterministic
        # order and prevents a stale deactivation from racing a rediscovery for this account.
        self.db.execute(
            select(AWSAccount.id).where(AWSAccount.id == account.id).with_for_update()
        ).scalar_one()
        at, created, updated = now_utc(), 0, 0
        seen: set[tuple[AssetType, str]] = set()
        for item in discovered:
            seen.add((item.asset_type, item.resource_id))
            asset = self.assets.by_identity(account.id, item.asset_type, item.resource_id)
            if asset is None:
                asset = Asset(
                    organization_id=account.organization_id,
                    aws_account_id=account.id,
                    asset_type=item.asset_type,
                    resource_id=item.resource_id,
                    first_seen_at=at,
                )
                self.db.add(asset)
                created += 1
            else:
                updated += 1
            asset.arn, asset.name, asset.region, asset.status = (
                item.arn,
                item.name,
                item.region,
                item.status,
            )
            asset.tags, asset.metadata_json, asset.last_seen_at, asset.is_active = (
                item.tags,
                json_safe(item.metadata),
                at,
                True,
            )
        deactivated = self.assets.deactivate_missing(account.id, asset_types, seen, at)
        self.db.flush()
        return created, updated, deactivated

    def _finish(
        self,
        job: DiscoveryJob,
        actor: User,
        status: DiscoveryJobStatus,
        errors: dict[str, str],
        *,
        service_results: dict[str, str] | None = None,
    ) -> DiscoveryJob:
        locked = self.db.scalar(
            select(DiscoveryJob)
            .where(DiscoveryJob.id == job.id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if locked is None:
            raise NotFoundError("discovery_job_not_found", "Discovery job was not found.")
        if locked.status != DiscoveryJobStatus.RUNNING:
            raise ConflictError(
                "discovery_job_not_running",
                "Only a running discovery job can reach a terminal state.",
            )
        job = locked
        job.status, job.finished_at = status, now_utc()
        job.error_summary = (
            "; ".join(f"{key}:{value}" for key, value in sorted(errors.items()))[:2000] or None
        )
        event = {
            DiscoveryJobStatus.COMPLETED: "aws.discovery.completed",
            DiscoveryJobStatus.PARTIALLY_COMPLETED: "aws.discovery.partially_completed",
            DiscoveryJobStatus.FAILED: "aws.discovery.failed",
        }[status]
        record_audit(
            self.db,
            event,
            "discovery_job",
            organization_id=job.organization_id,
            actor_user_id=actor.id,
            resource_id=job.id,
            result=AuditResult.FAILED
            if status == DiscoveryJobStatus.FAILED
            else AuditResult.SUCCEEDED,
            metadata={
                "aws_account_id": str(job.aws_account_id),
                "job_id": str(job.id),
                "assets_discovered": job.assets_discovered,
                "assets_created": job.assets_created,
                "assets_updated": job.assets_updated,
                "assets_deactivated": job.assets_deactivated,
                "service_results": service_results or errors,
            },
        )
        self.db.commit()
        self.db.refresh(job)
        return job
