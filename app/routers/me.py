from fastapi import APIRouter, HTTPException, Response, status

from app.core.security import hash_password, verify_password
from app.dependencies import CurrentUser, DbSession
from app.schemas.auth import ChangePasswordRequest
from app.schemas.user import MeResponse

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeResponse)
def me(current_user: CurrentUser):
    """The logged in user and their pharmacy."""
    return current_user


@router.patch(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={400: {"description": "Current password is incorrect, or the new one is the same"}},
)
def change_password(body: ChangePasswordRequest, current_user: CurrentUser, db: DbSession):
    """Change your own password. The current password is required, so a
    stolen token alone can't be used to take over the account."""
    if not verify_password(body.current_password, current_user.password_hash):
        # 400, not 401: the token is fine, so the client shouldn't log the user out
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must be different from the current one")

    current_user.password_hash = hash_password(body.new_password)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
