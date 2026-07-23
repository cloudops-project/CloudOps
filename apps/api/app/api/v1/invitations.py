from fastapi import APIRouter

from app.api.v1.organizations import member_response
from app.dependencies.auth import AppSettings, CurrentUser, DbSession
from app.schemas.invitation import InvitationAccept
from app.schemas.organization import MemberResponse
from app.services.invitations import InvitationService

router = APIRouter()


@router.post("/accept", response_model=MemberResponse)
def accept(
    payload: InvitationAccept, user: CurrentUser, db: DbSession, settings: AppSettings
) -> MemberResponse:
    member = InvitationService(db, settings).accept(payload.token, user)
    target = InvitationService(db, settings).repo.user(member.user_id)
    return member_response(member, target)  # type: ignore[arg-type]
