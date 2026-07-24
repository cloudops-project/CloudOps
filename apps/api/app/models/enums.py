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
    EC2_SECURITY_GROUP = "ec2_security_group"
    EBS_VOLUME = "ebs_volume"
    S3_BUCKET = "s3_bucket"
    IAM_USER = "iam_user"
    IAM_ROLE = "iam_role"
    IAM_GROUP = "iam_group"
    IAM_POLICY = "iam_policy"
    RDS_INSTANCE = "rds_instance"
    CLOUDWATCH_ALARM = "cloudwatch_alarm"
    CLOUDWATCH_LOG_GROUP = "cloudwatch_log_group"
    CLOUDTRAIL_TRAIL = "cloudtrail_trail"


class DiscoveryJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"


class RuleResultStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"
    ERROR = "error"


class FindingStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class EvaluationJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"


class FindingSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class ComplianceAssessmentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ComplianceControlStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_ASSESSED = "not_assessed"
    ERROR = "error"


class RiskPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskAssessmentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AITaskType(StrEnum):
    EXPLAIN_FINDING = "explain_finding"
    EXPLAIN_BUSINESS_IMPACT = "explain_business_impact"
    SUGGEST_REMEDIATION = "suggest_remediation"
    EXECUTIVE_SUMMARY = "executive_summary"
    JIRA_DESCRIPTION = "jira_description"
    EMAIL_SUMMARY = "email_summary"


class AIRequestStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AISourceType(StrEnum):
    FINDING = "finding"
    RISK_ASSESSMENT = "risk_assessment"
    COMPLIANCE_ASSESSMENT = "compliance_assessment"


class RiskCriticality(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class RiskEnvironment(StrEnum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    SANDBOX = "sandbox"
    UNKNOWN = "unknown"


class BusinessImpact(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class DataSensitivity(StrEnum):
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"
    INTERNAL = "internal"
    PUBLIC = "public"
    UNKNOWN = "unknown"


class RuleService(StrEnum):
    EC2 = "ec2"
    S3 = "s3"
    IAM = "iam"
    RDS = "rds"
    CLOUDWATCH = "cloudwatch"
    CLOUDWATCH_LOGS = "cloudwatch_logs"
    CLOUDTRAIL = "cloudtrail"


class RuleCategory(StrEnum):
    COVERAGE = "coverage"
    CREDENTIAL_HYGIENE = "credential_hygiene"
    DATA_PROTECTION = "data_protection"
    EXPOSURE = "exposure"
    HARDENING = "hardening"
    IDENTITY = "identity"
    INTEGRITY = "integrity"
    LEAST_PRIVILEGE = "least_privilege"
    LOGGING = "logging"
    MONITORING = "monitoring"
    NETWORK = "network"
    PATCHING = "patching"
    RESILIENCE = "resilience"
    TRANSPORT = "transport"
