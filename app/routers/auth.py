from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.errors import Conflict, ErrorResponse, NotAuthenticated
from app.core.security import DUMMY_HASH, create_access_token, verify_password
from app.dependencies import DbSession
from app.docs import examples
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import PharmacyResponse, RegisterResponse, UserResponse
from app.services.registration import register_pharmacy_with_owner
from app.services.users import EmailAlreadyRegistered

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS = "Incorrect email or password"


def invalid_credentials() -> NotAuthenticated:
    # The same 401 for an unknown email, a wrong password and an inactive user
    return NotAuthenticated(INVALID_CREDENTIALS)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: examples.response("The new pharmacy and its owner", examples.REGISTERED),
        409: examples.response(
            "Email already registered", examples.error("conflict", "Email already registered"), ErrorResponse
        ),
    },
)
def register(body: RegisterRequest, db: DbSession):
    """Sign up a new pharmacy: creates the pharmacy and its owner together."""
    try:
        owner = register_pharmacy_with_owner(
            db,
            pharmacy_name=body.pharmacy_name,
            full_name=body.full_name,
            email=body.email,
            password=body.password,
        )
    except EmailAlreadyRegistered:
        raise Conflict("Email already registered") from None
    return RegisterResponse(
        user=UserResponse.model_validate(owner),
        pharmacy=PharmacyResponse.model_validate(owner.pharmacy),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        200: examples.response("Logged in: use access_token as a Bearer token", examples.TOKEN),
        401: examples.response(
            INVALID_CREDENTIALS, examples.error("not_authenticated", INVALID_CREDENTIALS), ErrorResponse
        ),
    },
)
def login(body: LoginRequest, db: DbSession):
    """Log in with email and password. Paste the access_token into the
    Authorize button on /docs to call the other endpoints."""
    user = db.scalar(select(User).where(User.email == body.email))

    if user is None:
        # Spend the same time as checking a real password, so the response
        # time doesn't reveal whether the email has an account
        verify_password(body.password, DUMMY_HASH)
        raise invalid_credentials()
    # The password is checked even for inactive users, so they take the same time
    if not verify_password(body.password, user.password_hash) or not user.is_active:
        raise invalid_credentials()

    return TokenResponse(access_token=create_access_token(user.id, user.token_version))
