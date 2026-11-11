import uuid
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

JWT_ALGORITHM = "HS256"

# Argon2 is the recommended password hashing algorithm
password_hash = PasswordHash.recommended()

# A real hash of a throwaway password. Login checks against this when the
# email doesn't exist, so that case takes as long as a wrong password and
# the response time doesn't reveal which emails have accounts.
DUMMY_HASH = password_hash.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


class TokenClaims(NamedTuple):
    user_id: uuid.UUID
    # Must equal users.token_version, or the token has been revoked
    token_version: int


def create_access_token(user_id: uuid.UUID, token_version: int) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    # The JWT standard says "sub" must be a string. Only the user id and the
    # token version go in the token: role, pharmacy and is_active are always
    # read from the database.
    payload = {"sub": str(user_id), "ver": token_version, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> TokenClaims:
    """Return the user id and token version from a valid token.

    Raises jwt.InvalidTokenError if the signature is wrong, the token has
    expired, it wasn't signed with HS256, "sub" is missing or not a UUID, or
    "ver" is missing or not a whole number. Tokens made before token versions
    existed have no "ver", so they stop working too.
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        # Only accept HS256, so a token can't pick a weaker algorithm (e.g. "none")
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "sub", "ver"]},
    )
    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, TypeError, AttributeError) as exc:
        raise jwt.InvalidTokenError("sub is not a user id") from exc
    version = payload["ver"]
    # bool is a kind of int in Python, so rule it out explicitly
    if not isinstance(version, int) or isinstance(version, bool):
        raise jwt.InvalidTokenError("ver is not a token version")
    return TokenClaims(user_id, version)
