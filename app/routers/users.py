"""Owner-only user management: /api/v1/users.

Every route works inside the owner's own pharmacy. A user from another
pharmacy gets the same 404 as one that doesn't exist, so ids from other
pharmacies can't even be confirmed. Users are never deleted, only deactivated.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.errors import BadRequest, Conflict, ErrorResponse, NotFound
from app.core.paging import Page, Pagination, paginate, sort_param
from app.dependencies import DbSession, OwnerUser, require_owner
from app.models import Role, User
from app.schemas.user import UserResponse
from app.schemas.users import CreateUserRequest, ResetPasswordRequest, UpdateUserRequest
from app.services import users as service

# The router-level dependency guards every route here, including any added
# later: managers and staff get 403 before a route even runs.
router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_owner)],
    responses={
        401: {"model": ErrorResponse, "description": "Not logged in"},
        403: {"model": ErrorResponse, "description": "Only owners can manage users"},
    },
)

NOT_FOUND = {404: {"model": ErrorResponse, "description": "No such user in your pharmacy"}}
USER_NOT_FOUND = "User not found"

UserSort = sort_param(
    {"full_name": User.full_name, "email": User.email, "created_at": User.created_at},
    default="full_name",
    tie_breaker=User.id,
)


def pharmacy_user(user_id: uuid.UUID, owner: OwnerUser, db: DbSession) -> User:
    """The user in the URL, only if they belong to the owner's pharmacy."""
    user = service.get_pharmacy_user(db, owner.pharmacy_id, user_id)
    if user is None:
        raise NotFound(USER_NOT_FOUND)
    return user


PharmacyUser = Annotated[User, Depends(pharmacy_user)]


@router.get("", response_model=Page[UserResponse])
def list_users(
    owner: OwnerUser,
    db: DbSession,
    page: Pagination = Depends(),
    order_by: list = Depends(UserSort),
    role: Role | None = Query(None, description="Only users with this role"),
    is_active: bool | None = Query(None, description="Only active (true) or deactivated (false) users"),
    q: str | None = Query(None, min_length=1, max_length=100, description="Search full name and email"),
):
    """The users of your pharmacy, a page at a time."""
    query = service.users_query(owner.pharmacy_id, role=role, is_active=is_active, q=q)
    return paginate(db, query, page, order_by, UserResponse.model_validate)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse, "description": "Email already registered"}},
)
def create_user(body: CreateUserRequest, owner: OwnerUser, db: DbSession):
    """Add a user to your pharmacy with a starting password."""
    try:
        return service.create_user(
            db,
            pharmacy_id=owner.pharmacy_id,
            email=body.email,
            full_name=body.full_name,
            role=body.role,
            password=body.password,
        )
    except service.EmailAlreadyRegistered:
        raise Conflict("Email already registered") from None


@router.get("/{user_id}", response_model=UserResponse, responses=NOT_FOUND)
def get_user(user: PharmacyUser):
    return user


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    responses=NOT_FOUND | {409: {"model": ErrorResponse, "description": "Would remove the last active owner"}},
)
def update_user(body: UpdateUserRequest, user: PharmacyUser, db: DbSession):
    """Change a user's full name, role or active flag. Deactivate instead of deleting."""
    try:
        return service.update_user(db, user, full_name=body.full_name, role=body.role, is_active=body.is_active)
    except service.LastActiveOwner:
        raise Conflict(service.LAST_OWNER_MESSAGE) from None


OWN_PASSWORD_MESSAGE = "Use PATCH /api/v1/me/password to change your own password."


@router.post(
    "/{user_id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND | {400: {"model": ErrorResponse, "description": "You can't reset your own password here"}},
)
def reset_password(body: ResetPasswordRequest, user: PharmacyUser, owner: OwnerUser, db: DbSession):
    """Give another user a new starting password. Every token they had stops working.

    Not for your own account: that needs your current password, through
    PATCH /me/password, so a stolen token alone can't take the account over.
    """
    if user.id == owner.id:
        raise BadRequest(OWN_PASSWORD_MESSAGE)
    service.set_password(db, user, body.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
