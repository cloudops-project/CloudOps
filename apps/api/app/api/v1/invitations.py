from fastapi import APIRouter, Depends

from app.api.v1.organizations import member_response
from app.dependencies.auth import AppSettings, CurrentUser, DbSession, UserRateLimiter
from app.schemas.invitation import InvitationAccept
from app.schemas.organization import MemberResponse
from app.services.invitations import InvitationService

router = APIRouter()
_accept_rate_limit = UserRateLimiter("invitation_accept", limit=10, window_seconds=60)


@router.post(
    "/accept",
    response_model=MemberResponse,
    dependencies=[Depends(_accept_rate_limit)],
)
def accept(
    payload: InvitationAccept, user: CurrentUser, db: DbSession, settings: AppSettings
) -> MemberResponse:
    member = InvitationService(db, settings).accept(payload.token, user)
    target = InvitationService(db, settings).repo.user(member.user_id)
    return member_response(member, target)  # type: ignore[arg-type]
