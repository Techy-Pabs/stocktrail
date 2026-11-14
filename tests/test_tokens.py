"""Token versions: old tokens stop working after a password change or reset."""

from sqlalchemy import select

from app.core.security import decode_access_token
from app.models import Role, User
from tests.conftest import DEFAULT_PASSWORD
from tests.helpers import assert_unauthorized, bearer, headers_for

NEW_PASSWORD = "a-brand-new-password"


def change_own_password(client, headers, current=DEFAULT_PASSWORD, new=NEW_PASSWORD):
    return client.patch("/api/v1/me/password", headers=headers, json={"current_password": current, "new_password": new})


def test_new_users_start_at_token_version_0(register, db):
    register()

    assert db.scalar(select(User.token_version)) == 0


def test_login_token_carries_the_current_version(register, login, db):
    register()
    user = db.scalar(select(User))
    user.token_version = 4
    db.commit()

    assert decode_access_token(login().json()["access_token"]).token_version == 4


def test_after_changing_own_password_old_token_is_401_and_new_token_works(client, auth_headers, db):
    old_headers = auth_headers()

    response = change_own_password(client, old_headers)

    assert response.status_code == 200
    new_token = response.json()["access_token"]
    assert_unauthorized(client.get("/api/v1/me", headers=old_headers))
    assert client.get("/api/v1/me", headers=bearer(new_token)).status_code == 200
    assert db.scalar(select(User.token_version)) == 1


def test_changing_own_password_logs_out_every_other_session(client, auth_headers, login):
    phone = auth_headers()
    laptop = {"Authorization": f"Bearer {login().json()['access_token']}"}

    new_token = change_own_password(client, phone).json()["access_token"]

    assert_unauthorized(client.get("/api/v1/me", headers=phone))
    assert_unauthorized(client.get("/api/v1/me", headers=laptop))
    assert client.get("/api/v1/me", headers=bearer(new_token)).status_code == 200


def test_failed_password_change_keeps_existing_tokens(client, auth_headers, db):
    headers = auth_headers()

    assert change_own_password(client, headers, current="not-my-password").status_code == 400

    assert client.get("/api/v1/me", headers=headers).status_code == 200
    assert db.scalar(select(User.token_version)) == 0


def test_each_change_raises_the_version(client, auth_headers, db):
    headers = auth_headers()

    token = change_own_password(client, headers).json()["access_token"]
    change_own_password(client, bearer(token), current=NEW_PASSWORD, new="third-password-here")

    assert db.scalar(select(User.token_version)) == 2


def test_after_owner_reset_old_token_and_old_password_stop_working(client, make_pharmacy, make_user, login, db):
    pharmacy = make_pharmacy()
    owner = make_user(pharmacy, role=Role.OWNER)
    staff = make_user(pharmacy, role=Role.STAFF, email="sam@example.com")
    staff_headers = headers_for(staff)
    assert client.get("/api/v1/me", headers=staff_headers).status_code == 200

    response = client.post(
        f"/api/v1/users/{staff.id}/reset-password", json={"new_password": NEW_PASSWORD}, headers=headers_for(owner)
    )

    assert response.status_code == 204
    assert response.content == b""
    assert_unauthorized(client.get("/api/v1/me", headers=staff_headers))
    assert login("sam@example.com", DEFAULT_PASSWORD).status_code == 401
    new_login = login("sam@example.com", NEW_PASSWORD)
    assert new_login.status_code == 200
    assert client.get("/api/v1/me", headers=bearer(new_login.json()["access_token"])).status_code == 200
    db.expire_all()
    assert db.get(User, staff.id).token_version == 1


def test_owner_reset_doesnt_affect_the_owners_own_token(client, make_pharmacy, make_user):
    pharmacy = make_pharmacy()
    owner = make_user(pharmacy, role=Role.OWNER)
    staff = make_user(pharmacy)
    owner_headers = headers_for(owner)

    client.post(f"/api/v1/users/{staff.id}/reset-password", json={"new_password": NEW_PASSWORD}, headers=owner_headers)

    assert client.get("/api/v1/me", headers=owner_headers).status_code == 200


def test_token_with_a_future_version_is_rejected(client, make_pharmacy, make_user):
    # Only an exact match counts, so a forged or stale number never works
    user = make_user(make_pharmacy())
    user.token_version += 1

    assert_unauthorized(client.get("/api/v1/me", headers=headers_for(user)))
