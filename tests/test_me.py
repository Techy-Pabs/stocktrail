import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import delete, select, update

from app.core.config import settings
from app.core.security import JWT_ALGORITHM, create_access_token
from app.models import Pharmacy, User

UNAUTHORIZED = {"detail": "Could not validate credentials"}


def assert_unauthorized(response):
    # Every auth failure looks exactly like this
    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED
    assert response.headers["WWW-Authenticate"] == "Bearer"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_me_returns_user_and_pharmacy(client, auth_headers, db):
    headers = auth_headers(email="ada@example.com")

    response = client.get("/api/v1/me", headers=headers)

    assert response.status_code == 200
    user = db.scalar(select(User))
    pharmacy = db.scalar(select(Pharmacy))
    assert response.json() == {
        "id": str(user.id),
        "email": "ada@example.com",
        "full_name": "Ada Obi",
        "role": "owner",
        "pharmacy": {"id": str(pharmacy.id), "name": "Ada Pharmacy"},
    }


def test_me_without_token_returns_401(client):
    assert_unauthorized(client.get("/api/v1/me"))


@pytest.mark.parametrize(
    "token",
    [
        "not-a-real-token",
        # Right shape, wrong signing key
        jwt.encode({"sub": str(uuid.uuid4()), "exp": datetime.now(UTC) + timedelta(minutes=5)}, "x" * 40, "HS256"),
        # Unsigned ("none" algorithm)
        jwt.encode({"sub": str(uuid.uuid4()), "exp": datetime.now(UTC) + timedelta(minutes=5)}, None, "none"),
    ],
    ids=["garbage", "wrong-key", "alg-none"],
)
def test_me_with_bad_token_returns_401(client, token):
    assert_unauthorized(client.get("/api/v1/me", headers=bearer(token)))


def test_me_with_expired_token_returns_401(client, register, db):
    register()
    user_id = db.scalar(select(User.id))
    expired = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(UTC) - timedelta(seconds=1)},
        settings.jwt_secret_key,
        JWT_ALGORITHM,
    )

    assert_unauthorized(client.get("/api/v1/me", headers=bearer(expired)))


@pytest.mark.parametrize("sub", ["123", "not-a-uuid"])
def test_me_with_token_whose_sub_is_not_a_uuid_returns_401(client, sub):
    token = jwt.encode(
        {"sub": sub, "exp": datetime.now(UTC) + timedelta(minutes=5)}, settings.jwt_secret_key, JWT_ALGORITHM
    )

    assert_unauthorized(client.get("/api/v1/me", headers=bearer(token)))


def test_me_for_deleted_user_returns_401(client, auth_headers, db):
    headers = auth_headers()
    db.execute(delete(User))
    db.commit()

    assert_unauthorized(client.get("/api/v1/me", headers=headers))


def test_inactive_user_is_rejected_even_with_a_valid_token(client, auth_headers, db):
    headers = auth_headers()
    assert client.get("/api/v1/me", headers=headers).status_code == 200

    # Deactivated after logging in: the token is still valid, but the user
    # is loaded from the database on every request, so it stops working now
    db.execute(update(User).values(is_active=False))
    db.commit()

    assert_unauthorized(client.get("/api/v1/me", headers=headers))
    assert_unauthorized(
        client.patch(
            "/api/v1/me/password",
            headers=headers,
            json={"current_password": "correct-horse-battery", "new_password": "another-good-password"},
        )
    )


def test_role_comes_from_database_not_token(client, auth_headers, db):
    headers = auth_headers()
    db.execute(update(User).values(role="staff"))
    db.commit()

    assert client.get("/api/v1/me", headers=headers).json()["role"] == "staff"


def test_token_contains_only_user_id_and_expiry():
    user_id = uuid.uuid4()
    payload = jwt.decode(create_access_token(user_id), settings.jwt_secret_key, algorithms=[JWT_ALGORITHM])

    assert set(payload) == {"sub", "exp"}
    assert payload["sub"] == str(user_id)
