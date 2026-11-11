from fastapi import APIRouter

from app.core.errors import BadRequest, ErrorResponse
from app.core.security import create_access_token, verify_password
from app.dependencies import CurrentUser, DbSession
from app.schemas.auth import ChangePasswordRequest, TokenResponse
from app.schemas.user import MeResponse
from app.services.users import set_password

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeResponse)
def me(current_user: CurrentUser):
    """The logged in user and their pharmacy."""
    return current_user


@router.patch(
    "/password",
    response_model=TokenResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Current password is incorrect, or the new one is the same"}
    },
)
def change_password(body: ChangePasswordRequest, current_user: CurrentUser, db: DbSession):
    """Change your own password. The current password is required, so a
    stolen token alone can't be used to take over the account.

    Every token you had stops working, including the one used for this
    request. The response has a new token, so you stay logged in here.
    """
    if not verify_password(body.current_password, current_user.password_hash):
        # 400, not 401: the token is fine, so the client shouldn't log the user out
        raise BadRequest("Current password is incorrect")
    if body.new_password == body.current_password:
        raise BadRequest("New password must be different from the current one")

    new_version = set_password(db, current_user, body.new_password)
    return TokenResponse(access_token=create_access_token(current_user.id, new_version))
