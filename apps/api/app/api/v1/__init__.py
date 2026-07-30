from fastapi import APIRouter

from app.api.v1 import (
    ai,
    audit,
    auth,
    aws_accounts,
    compliance,
    dashboard,
    discovery,
    invitations,
    jira,
    notifications,
    organizations,
    platform_jobs,
    remediation,
    risk,
    scheduler,
    security_findings,
)

router = APIRouter()
router.include_router(ai.router, tags=["ai-assistant"])
router.include_router(auth.router, prefix="/auth", tags=["authentication"])
router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
router.include_router(invitations.router, prefix="/invitations", tags=["invitations"])
router.include_router(aws_accounts.router, prefix="/aws", tags=["aws-onboarding"])
router.include_router(discovery.router, tags=["asset-discovery"])
router.include_router(security_findings.router, tags=["security-findings"])
router.include_router(compliance.router, tags=["compliance"])
router.include_router(risk.router, tags=["risk"])
router.include_router(notifications.router, tags=["notifications"])
router.include_router(remediation.router, tags=["remediation"])
router.include_router(jira.router, tags=["jira-integration"])
router.include_router(scheduler.router, tags=["scheduler"])
router.include_router(platform_jobs.router, tags=["platform-jobs"])
router.include_router(audit.router, tags=["audit"])
router.include_router(dashboard.router, tags=["dashboard"])
