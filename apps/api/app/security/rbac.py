from __future__ import annotations

from enum import StrEnum

from app.exceptions.errors import ForbiddenError
from app.models.enums import OrganizationRole


class Capability(StrEnum):
    ORGANIZATION_READ = "organization.read"
    ORGANIZATION_UPDATE = "organization.update"
    MEMBERS_READ = "members.read"
    MEMBERS_MANAGE = "members.manage"
    INVITATIONS_MANAGE = "invitations.manage"
    AUDIT_READ = "audit.read"
    AWS_ACCOUNTS_MANAGE = "aws_accounts.manage"
    AWS_ACCOUNTS_READ = "aws_accounts.read"
    DISCOVERY_START = "discovery.start"
    ASSETS_READ = "assets.read"
    RULES_READ = "rules.read"
    EVALUATIONS_START = "evaluations.start"
    FINDINGS_READ = "findings.read"
    FINDINGS_SUPPRESS = "findings.suppress"
    COMPLIANCE_READ = "compliance.read"
    COMPLIANCE_ASSESS = "compliance.assess"
    RISK_READ = "risk.read"
    RISK_ASSESS = "risk.assess"
    RISK_CONTEXT_MANAGE = "risk.context.manage"
    RISK_CONTROLS_MANAGE = "risk.controls.manage"
    AI_READ = "ai.read"
    AI_GENERATE = "ai.generate"
    NOTIFICATIONS_READ = "notifications.read"
    NOTIFICATIONS_APPROVE = "notifications.approve"
    REMEDIATION_READ = "remediation.read"
    REMEDIATION_REQUEST = "remediation.request"
    REMEDIATION_APPROVE = "remediation.approve"
    REMEDIATION_REJECT = "remediation.reject"
    REMEDIATION_EXECUTE = "remediation.execute"
    REMEDIATION_ADMIN = "remediation.admin"
    SCHEDULE_READ = "schedule.read"
    SCHEDULE_MANAGE = "schedule.manage"
    JOBS_READ = "jobs.read"
    JOBS_MANAGE = "jobs.manage"
    JIRA_MANAGE = "jira.manage"
    JIRA_READ = "jira.read"


ROLE_CAPABILITIES: dict[OrganizationRole, frozenset[Capability]] = {
    OrganizationRole.OWNER: frozenset(Capability),
    OrganizationRole.ADMIN: frozenset(
        {
            Capability.ORGANIZATION_READ,
            Capability.ORGANIZATION_UPDATE,
            Capability.MEMBERS_READ,
            Capability.MEMBERS_MANAGE,
            Capability.INVITATIONS_MANAGE,
            Capability.AUDIT_READ,
            Capability.AWS_ACCOUNTS_MANAGE,
            Capability.AWS_ACCOUNTS_READ,
            Capability.RULES_READ,
            Capability.EVALUATIONS_START,
            Capability.FINDINGS_READ,
            Capability.FINDINGS_SUPPRESS,
            Capability.COMPLIANCE_READ,
            Capability.COMPLIANCE_ASSESS,
            Capability.RISK_READ,
            Capability.RISK_ASSESS,
            Capability.RISK_CONTEXT_MANAGE,
            Capability.RISK_CONTROLS_MANAGE,
            Capability.DISCOVERY_START,
            Capability.ASSETS_READ,
            Capability.AI_READ,
            Capability.AI_GENERATE,
            Capability.NOTIFICATIONS_READ,
            Capability.NOTIFICATIONS_APPROVE,
            Capability.REMEDIATION_READ,
            Capability.REMEDIATION_REQUEST,
            Capability.REMEDIATION_APPROVE,
            Capability.REMEDIATION_REJECT,
            Capability.REMEDIATION_EXECUTE,
            Capability.SCHEDULE_READ,
            Capability.SCHEDULE_MANAGE,
            Capability.JOBS_READ,
            Capability.JOBS_MANAGE,
            Capability.JIRA_MANAGE,
            Capability.JIRA_READ,
        }
    ),
    OrganizationRole.SECURITY_ANALYST: frozenset(
        {
            Capability.ORGANIZATION_READ,
            Capability.MEMBERS_READ,
            Capability.DISCOVERY_START,
            Capability.ASSETS_READ,
            Capability.AWS_ACCOUNTS_READ,
            Capability.RULES_READ,
            Capability.EVALUATIONS_START,
            Capability.FINDINGS_READ,
            Capability.FINDINGS_SUPPRESS,
            Capability.COMPLIANCE_READ,
            Capability.COMPLIANCE_ASSESS,
            Capability.RISK_READ,
            Capability.RISK_ASSESS,
            Capability.RISK_CONTEXT_MANAGE,
            Capability.RISK_CONTROLS_MANAGE,
            Capability.AI_READ,
            Capability.AI_GENERATE,
            Capability.NOTIFICATIONS_READ,
            Capability.NOTIFICATIONS_APPROVE,
            Capability.REMEDIATION_READ,
            Capability.REMEDIATION_REQUEST,
            Capability.REMEDIATION_APPROVE,
            Capability.REMEDIATION_REJECT,
            Capability.REMEDIATION_EXECUTE,
            Capability.SCHEDULE_READ,
            Capability.SCHEDULE_MANAGE,
            Capability.JOBS_READ,
            Capability.JOBS_MANAGE,
        }
    ),
    OrganizationRole.CLOUD_ENGINEER: frozenset(
        {
            Capability.ORGANIZATION_READ,
            Capability.MEMBERS_READ,
            Capability.DISCOVERY_START,
            Capability.ASSETS_READ,
            Capability.AWS_ACCOUNTS_READ,
            Capability.RULES_READ,
            Capability.EVALUATIONS_START,
            Capability.FINDINGS_READ,
            Capability.COMPLIANCE_READ,
            Capability.COMPLIANCE_ASSESS,
            Capability.RISK_READ,
            Capability.RISK_ASSESS,
            Capability.AI_READ,
            Capability.AI_GENERATE,
            Capability.NOTIFICATIONS_READ,
            Capability.REMEDIATION_READ,
            Capability.REMEDIATION_REQUEST,
            Capability.SCHEDULE_READ,
            Capability.SCHEDULE_MANAGE,
            Capability.JOBS_READ,
            Capability.JOBS_MANAGE,
        }
    ),
    OrganizationRole.AUDITOR: frozenset(
        {
            Capability.ORGANIZATION_READ,
            Capability.MEMBERS_READ,
            Capability.AUDIT_READ,
            Capability.ASSETS_READ,
            Capability.RULES_READ,
            Capability.FINDINGS_READ,
            Capability.COMPLIANCE_READ,
            Capability.RISK_READ,
            Capability.AI_READ,
            Capability.NOTIFICATIONS_READ,
            Capability.REMEDIATION_READ,
            Capability.SCHEDULE_READ,
            Capability.JOBS_READ,
        }
    ),
    OrganizationRole.VIEWER: frozenset(
        {
            Capability.ORGANIZATION_READ,
            Capability.ASSETS_READ,
            Capability.AWS_ACCOUNTS_READ,
            Capability.RULES_READ,
            Capability.FINDINGS_READ,
            Capability.COMPLIANCE_READ,
            Capability.RISK_READ,
            Capability.AI_READ,
            Capability.NOTIFICATIONS_READ,
            Capability.REMEDIATION_READ,
            Capability.SCHEDULE_READ,
            Capability.JOBS_READ,
        }
    ),
}


def role_has_capability(role: OrganizationRole, capability: Capability) -> bool:
    return capability in ROLE_CAPABILITIES[role]


def can_assign_role(actor: OrganizationRole, target: OrganizationRole) -> bool:
    if actor == OrganizationRole.OWNER:
        return True
    return actor == OrganizationRole.ADMIN and target != OrganizationRole.OWNER


def ensure_actor_can_manage_membership(
    *,
    actor_role: OrganizationRole,
    target_role: OrganizationRole,
    requested_role: OrganizationRole | None = None,
) -> None:
    """Enforce governance boundaries independently from last-owner invariants."""
    if actor_role not in {OrganizationRole.OWNER, OrganizationRole.ADMIN}:
        raise ForbiddenError()
    if target_role == OrganizationRole.OWNER and actor_role != OrganizationRole.OWNER:
        raise ForbiddenError(
            "owner_management_forbidden", "Only an owner can manage another owner."
        )
    if requested_role == OrganizationRole.OWNER and actor_role != OrganizationRole.OWNER:
        raise ForbiddenError(
            "owner_assignment_forbidden", "Only an owner can assign the owner role."
        )
