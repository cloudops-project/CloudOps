from fastapi import APIRouter

from app.api.v1 import (
    auth,
    aws_accounts,
    discovery,
    invitations,
    organizations,
    security_findings,
)

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["authentication"])
router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
router.include_router(invitations.router, prefix="/invitations", tags=["invitations"])
router.include_router(aws_accounts.router, prefix="/aws", tags=["aws-onboarding"])
router.include_router(discovery.router, tags=["asset-discovery"])
router.include_router(security_findings.router, tags=["security-findings"])
