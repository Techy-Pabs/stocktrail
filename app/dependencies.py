from collections.abc import Callable, Generator
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotAuthenticated
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models import Role, User

# Reads "Authorization: Bearer <token>" and adds the Authorize button to /docs.
# auto_error=False lets us send our own 401 instead of FastAPI's default.
bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session]:
    # One session per request, closed afterwards even if the request fails
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


def unauthorized() -> NotAuthenticated:
    """The one 401 sent for every token failure.

    Missing, forged, expired or revoked token, deleted user, inactive user:
    all get exactly this, so a caller can't tell which one happened.
    """
    return NotAuthenticated("Could not validate credentials")


def get_current_user(
    db: DbSession,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    """The logged in user, loaded fresh from the database on every request.

    The token only says who the user is and which token version it was made
    with. Whether they still exist, are still active, their role and their
    pharmacy all come from the database, so deactivating someone or changing
    their role takes effect immediately. A token whose version is older than
    the user's (the password changed since) is refused.

    This is also where every request's pharmacy comes from: routes use
    current_user.pharmacy_id and never accept a pharmacy_id from the client.
    """
    if credentials is None:
        raise unauthorized()
    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.InvalidTokenError:
        raise unauthorized() from None

    user = db.get(User, claims.user_id)
    if user is None or not user.is_active or user.token_version != claims.token_version:
        raise unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[[User], User]:
    """A dependency allowing only users with one of these roles; others get 403.

    The role checked is the one loaded from the database by get_current_user,
    never anything in the token. Not logged in is still the usual 401.

        require_owner = require_roles(Role.OWNER)
        OwnerUser = Annotated[User, Depends(require_owner)]
    """
    allowed = frozenset(roles)

    def check_role(current_user: CurrentUser) -> User:
        if current_user.role not in allowed:
            raise Forbidden()
        return current_user

    return check_role


require_owner = require_roles(Role.OWNER)
OwnerUser = Annotated[User, Depends(require_owner)]

# Who may change the product catalogue (and, later, stock)
require_owner_or_manager = require_roles(Role.OWNER, Role.MANAGER)
OwnerOrManager = Annotated[User, Depends(require_owner_or_manager)]
