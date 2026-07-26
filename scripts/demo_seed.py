from __future__ import annotations

# ruff: noqa: E402, I001

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import select
from sqlalchemy.engine.url import make_url
from sqlalchemy.sql import text

from app.core.config import get_settings
from app.db.base import Base, utc_now
from app.db.session import SessionLocal
from app.models import (
    AWSAccount,
    AWSExternalIDReservation,
    Asset,
    Finding,
    NotificationEvent,
    Organization,
    OrganizationMembership,
    User,
)
from app.models.enums import (
    AWSAccountStatus,
    AssetType,
    FindingSeverity,
    MembershipStatus,
    NotificationStatus,
    OrganizationRole,
    UserStatus,
)
from app.security.passwords import hash_password
from app.services.common import normalize_email
from app.services.compliance import ComplianceService
from app.services.evaluations import EvaluationService
from app.services.notifications import NotificationService
from app.services.remediation import RemediationService
from app.services.risk import RiskService
from app.services.scheduler import SchedulerService


DEMO_EMAIL = "owner@cloudops-demo.testmail.com"
DEMO_ANALYST_EMAIL = "analyst@cloudops-demo.testmail.com"
DEMO_ENGINEER_EMAIL = "engineer@cloudops-demo.testmail.com"
DEMO_PASSWORD = "CloudOps-Demo-Password-123!"
DEMO_ORG_SLUG = "cloudops-demo"
DEMO_ACCOUNT_ID = "123456789012"


def _assert_demo_database() -> None:
    settings = get_settings()
    database_name = make_url(settings.database_url).database or ""
    if settings.app_env == "production":
        raise SystemExit("Refusing to seed or reset demo data with APP_ENV=production.")
    if database_name != "cloudops_demo" and not database_name.startswith("cloudops_demo_"):
        raise SystemExit("Refusing to seed or reset demo data outside a cloudops_demo* database.")


def _reset_database() -> None:
    with SessionLocal() as db:
        table_names = ", ".join(
            f'"{table.name.replace(chr(34), chr(34) + chr(34))}"'
            for table in Base.metadata.sorted_tables
        )
        db.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
        db.commit()


def _seed_demo(*, deliver_email: bool) -> dict[str, object]:
    settings = get_settings()
    with SessionLocal() as db:
        now = utc_now()
        owner = User(
            email=DEMO_EMAIL,
            normalized_email=normalize_email(DEMO_EMAIL),
            password_hash=hash_password(DEMO_PASSWORD),
            full_name="CloudOps Demo Owner",
            status=UserStatus.ACTIVE,
            email_verified_at=now,
        )
        db.add(owner)
        db.flush()
        analyst = User(
            email=DEMO_ANALYST_EMAIL,
            normalized_email=normalize_email(DEMO_ANALYST_EMAIL),
            password_hash=hash_password(DEMO_PASSWORD),
            full_name="CloudOps Demo Analyst",
            status=UserStatus.ACTIVE,
            email_verified_at=now,
        )
        db.add(analyst)
        db.flush()
        engineer = User(
            email=DEMO_ENGINEER_EMAIL,
            normalized_email=normalize_email(DEMO_ENGINEER_EMAIL),
            password_hash=hash_password(DEMO_PASSWORD),
            full_name="CloudOps Demo Engineer",
            status=UserStatus.ACTIVE,
            email_verified_at=now,
        )
        db.add(engineer)
        db.flush()
        organization = Organization(
            name="CloudOps Demo",
            slug=DEMO_ORG_SLUG,
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
                joined_at=now,
            )
        )
        db.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=analyst.id,
                role=OrganizationRole.SECURITY_ANALYST,
                status=MembershipStatus.ACTIVE,
                joined_at=now,
            )
        )
        db.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=engineer.id,
                role=OrganizationRole.CLOUD_ENGINEER,
                status=MembershipStatus.ACTIVE,
                joined_at=now,
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
            last_validated_at=now,
            created_by_user_id=owner.id,
        )
        db.add(account)
        db.flush()
        db.add(
            AWSExternalIDReservation(
                external_id=account.external_id,
                organization_id=organization.id,
                aws_account_id=account.id,
            )
        )
        assets = [
            Asset(
                organization_id=organization.id,
                aws_account_id=account.id,
                asset_type=AssetType.EC2_INSTANCE,
                resource_id="i-demo-unencrypted",
                arn=f"arn:aws:ec2:us-east-1:{DEMO_ACCOUNT_ID}:instance/i-demo-unencrypted",
                name="demo-unencrypted-instance",
                region="us-east-1",
                status="active",
                metadata_json={
                    "state": "running",
                    "public_ip": "203.0.113.10",
                    "imds_v2_required": False,
                    "synthetic": True,
                },
            ),
            Asset(
                organization_id=organization.id,
                aws_account_id=account.id,
                asset_type=AssetType.CLOUDTRAIL_TRAIL,
                resource_id="demo-cloudtrail-disabled",
                arn=f"arn:aws:cloudtrail:us-east-1:{DEMO_ACCOUNT_ID}:trail/demo-disabled",
                name="demo-disabled-trail",
                region="us-east-1",
                status="disabled",
                metadata_json={"is_logging": False, "synthetic": True},
            ),
            Asset(
                organization_id=organization.id,
                aws_account_id=account.id,
                asset_type=AssetType.S3_BUCKET,
                resource_id="demo-public-bucket",
                arn="arn:aws:s3:::demo-public-bucket",
                name="demo-public-bucket",
                region="global",
                status="active",
                metadata_json={
                    "public_access_block": False,
                    "encryption_enabled": False,
                    "synthetic": True,
                },
            ),
            Asset(
                organization_id=organization.id,
                aws_account_id=account.id,
                asset_type=AssetType.EC2_SECURITY_GROUP,
                resource_id="sg-demo-open-ssh",
                arn=f"arn:aws:ec2:us-east-1:{DEMO_ACCOUNT_ID}:security-group/sg-demo-open-ssh",
                name="demo-open-ssh",
                region="us-east-1",
                status="active",
                metadata_json={
                    "ingress": [
                        {
                            "ip_protocol": "tcp",
                            "from_port": 22,
                            "to_port": 22,
                            "cidr_ipv4": "0.0.0.0/0",
                        }
                    ],
                    "synthetic": True,
                },
            ),
            Asset(
                organization_id=organization.id,
                aws_account_id=account.id,
                asset_type=AssetType.IAM_USER,
                resource_id="demo-admin-user",
                arn=f"arn:aws:iam::{DEMO_ACCOUNT_ID}:user/demo-admin-user",
                name="demo-admin-user",
                region="global",
                status="active",
                metadata_json={
                    "console_access": True,
                    "mfa_enabled": False,
                    "active_key_created_at": ["2025-01-01T00:00:00Z"],
                    "attached_policy_arns": ["arn:aws:iam::aws:policy/AdministratorAccess"],
                    "inline_policy_documents": [
                        {
                            "Statement": {
                                "Effect": "Allow",
                                "Action": "*",
                                "Resource": "*",
                            }
                        }
                    ],
                    "synthetic": True,
                },
            ),
        ]
        db.add_all(assets)
        db.commit()

        evaluation = EvaluationService(db).start(account.id, analyst)
        compliance = ComplianceService(db).assess(account.id, owner, "cis_aws", None, evaluation.id)
        risk = RiskService(db).assess(organization.id, owner, aws_account_id=account.id)
        schedule = SchedulerService(db, settings).create_schedule(
            organization.id,
            account.id,
            owner,
            name="Daily demo scan",
            interval_minutes=1440,
        )
        first_finding = db.scalar(
            select(Finding)
            .where(Finding.organization_id == organization.id)
            .order_by((Finding.severity == FindingSeverity.CRITICAL).desc(), Finding.created_at)
        )
        remediation_id = None
        if first_finding is not None:
            remediation = RemediationService(db).propose_for_finding(
                organization.id, first_finding.id, owner
            )
            remediation_id = str(remediation.id)

        delivered_notification_id = None
        if deliver_email:
            event = db.scalar(
                select(NotificationEvent).where(
                    NotificationEvent.organization_id == organization.id,
                    NotificationEvent.status == NotificationStatus.PENDING_APPROVAL,
                )
            )
            if event is not None:
                notification_service = NotificationService(db)
                notification_service.approve(organization.id, event.id, owner)
                db.commit()
                notification_service.deliver(organization.id, event.id)
                db.commit()
                delivered_notification_id = str(event.id)

        return {
            "email": DEMO_EMAIL,
            "analyst_email": DEMO_ANALYST_EMAIL,
            "engineer_email": DEMO_ENGINEER_EMAIL,
            "password": DEMO_PASSWORD,
            "organization_id": str(organization.id),
            "organization_slug": organization.slug,
            "aws_account_id": str(account.id),
            "evaluation_id": str(evaluation.id),
            "compliance_assessment_id": str(compliance.id),
            "risk_assessment_id": str(risk.id),
            "schedule_id": str(schedule.id),
            "remediation_request_id": remediation_id,
            "delivered_notification_id": delivered_notification_id,
            "synthetic_assets": len(assets),
            "mailpit_url": "http://localhost:8025",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the guarded local CloudOps demo database.")
    parser.add_argument("--reset", action="store_true", help="Delete all rows from cloudops_demo*.")
    parser.add_argument(
        "--deliver-email",
        action="store_true",
        help="Approve and deliver one notification through the configured provider.",
    )
    args = parser.parse_args()
    _assert_demo_database()
    if args.reset:
        _reset_database()
    summary = _seed_demo(deliver_email=args.deliver_email)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
