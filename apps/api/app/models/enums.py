from enum import StrEnum


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_type]


class UserStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class OrganizationRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    SECURITY_ANALYST = "security_analyst"
    CLOUD_ENGINEER = "cloud_engineer"
    AUDITOR = "auditor"
    VIEWER = "viewer"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class AuditResult(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"


class AWSAccountStatus(StrEnum):
    PENDING = "pending"
    CONNECTED = "connected"
    FAILED = "failed"
    DISCONNECTED = "disconnected"


class AssetType(StrEnum):
    EC2_INSTANCE = "ec2_instance"
    S3_BUCKET = "s3_bucket"
    IAM_USER = "iam_user"
    IAM_ROLE = "iam_role"
    IAM_GROUP = "iam_group"
    IAM_POLICY = "iam_policy"
    RDS_INSTANCE = "rds_instance"


class DiscoveryJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
