"""Owner-only user management: /api/v1/users."""

import pytest
from sqlalchemy import select

from app.models import Role, User
from tests.conftest import DEFAULT_PASSWORD
from tests.helpers import assert_error, assert_unauthorized, headers_for

NEW_USER = {"email": "Bola@Example.com", "full_name": "Bola Ade", "role": "staff", "password": "starting-password"}


@pytest.fixture
def pharmacy(make_pharmacy):
    return make_pharmacy("Ada Pharmacy")


@pytest.fixture
def owner(pharmacy, make_user):
    return make_user(pharmacy, role=Role.OWNER, full_name="Ada Owner", email="ada@example.com")


@pytest.fixture
def staff(pharmacy, make_user):
    return make_user(pharmacy, role=Role.STAFF, full_name="Sam Staff", email="sam@example.com")


def every_users_route(target_id):
    """(method, path, body) for every /users route."""
    return [
        ("GET", "/api/v1/users", None),
        ("POST", "/api/v1/users", NEW_USER),
        ("GET", f"/api/v1/users/{target_id}", None),
        ("PATCH", f"/api/v1/users/{target_id}", {"full_name": "New Name"}),
        ("POST", f"/api/v1/users/{target_id}/reset-password", {"new_password": "another-password"}),
    ]


ROUTE_IDS = ["list", "create", "get", "update", "reset-password"]


# --- Roles -------------------------------------------------------------------


@pytest.mark.parametrize("route", range(5), ids=ROUTE_IDS)
def test_owner_is_allowed_on_every_users_route(client, owner, staff, route):
    method, path, body = every_users_route(staff.id)[route]

    response = client.request(method, path, json=body, headers=headers_for(owner))

    assert response.status_code in (200, 201, 204), response.text


@pytest.mark.parametrize("role", [Role.MANAGER, Role.STAFF])
@pytest.mark.parametrize("route", range(5), ids=ROUTE_IDS)
def test_managers_and_staff_get_403_on_every_users_route(client, pharmacy, make_user, staff, db, role, route):
    caller = make_user(pharmacy, role=role)
    method, path, body = every_users_route(staff.id)[route]

    response = client.request(method, path, json=body, headers=headers_for(caller))

    assert_error(response, 403, "forbidden")
    # Nothing changed
    db.expire_all()
    assert db.get(User, staff.id).full_name == "Sam Staff"
    assert db.scalar(select(User).where(User.email == "bola@example.com")) is None


@pytest.mark.parametrize("route", range(5), ids=ROUTE_IDS)
def test_not_logged_in_gets_401_on_every_users_route(client, staff, route):
    method, path, body = every_users_route(staff.id)[route]

    assert_unauthorized(client.request(method, path, json=body))


def test_role_comes_from_the_database_not_the_token(client, owner, db):
    headers = headers_for(owner)
    assert client.get("/api/v1/users", headers=headers).status_code == 200

    # Demoted after the token was made: the same token now gets 403
    owner.role = Role.MANAGER
    db.commit()

    assert_error(client.get("/api/v1/users", headers=headers), 403, "forbidden")


def test_no_route_deletes_users(client, owner, staff):
    response = client.delete(f"/api/v1/users/{staff.id}", headers=headers_for(owner))

    assert_error(response, 405, "method_not_allowed")


# --- Tenant isolation --------------------------------------------------------


@pytest.fixture
def other_pharmacy_user(make_pharmacy, make_user):
    other = make_pharmacy("Other Pharmacy")
    make_user(other, role=Role.OWNER, full_name="Olu Other Owner")
    return make_user(other, role=Role.STAFF, full_name="Zed Searchable", email="zed@other.example.com")


@pytest.mark.parametrize(
    "method, suffix, body",
    [
        ("GET", "", None),
        ("PATCH", "", {"full_name": "Hijacked"}),
        ("PATCH", "", {"is_active": False}),
        ("POST", "/reset-password", {"new_password": "hijacked-password"}),
    ],
    ids=["get", "rename", "deactivate", "reset-password"],
)
def test_other_pharmacys_user_is_404(client, db, owner, other_pharmacy_user, method, suffix, body):
    response = client.request(
        method, f"/api/v1/users/{other_pharmacy_user.id}{suffix}", json=body, headers=headers_for(owner)
    )

    # 404, the same as a user that doesn't exist: never 403
    assert_error(response, 404, "not_found", "User not found")
    db.expire_all()
    untouched = db.get(User, other_pharmacy_user.id)
    assert (untouched.full_name, untouched.is_active, untouched.token_version) == ("Zed Searchable", True, 0)


def test_other_pharmacys_users_never_appear_in_the_list_or_search(client, owner, staff, other_pharmacy_user):
    headers = headers_for(owner)

    everyone = client.get("/api/v1/users", headers=headers, params={"limit": 100}).json()
    assert {item["id"] for item in everyone["items"]} == {str(owner.id), str(staff.id)}
    assert everyone["total"] == 2

    for q in ("Zed", "zed@other", "other.example.com", "Other"):
        found = client.get("/api/v1/users", headers=headers, params={"q": q}).json()
        assert found["items"] == [] and found["total"] == 0, q


def test_created_user_joins_the_owners_pharmacy(client, owner, other_pharmacy_user, db):
    response = client.post("/api/v1/users", json=NEW_USER, headers=headers_for(owner))

    assert response.status_code == 201
    created = db.get(User, response.json()["id"])
    assert created.pharmacy_id == owner.pharmacy_id


# --- Listing filters ---------------------------------------------------------


def test_filters_role_and_is_active(client, pharmacy, owner, make_user):
    manager = make_user(pharmacy, role=Role.MANAGER)
    inactive = make_user(pharmacy, role=Role.STAFF, is_active=False)
    headers = headers_for(owner)

    def ids(**params):
        return {item["id"] for item in client.get("/api/v1/users", headers=headers, params=params).json()["items"]}

    assert ids(role="manager") == {str(manager.id)}
    assert ids(is_active="false") == {str(inactive.id)}
    assert ids(role="owner", is_active="true") == {str(owner.id)}
    assert_error(client.get("/api/v1/users", headers=headers, params={"role": "admin"}), 422, "validation_error")


def test_search_matches_name_or_email_case_insensitively(client, pharmacy, owner, make_user):
    chidi = make_user(pharmacy, full_name="Chidi Okeke", email="c.okeke@example.com")
    make_user(pharmacy, full_name="Ngozi Eze", email="ngozi@example.com")
    headers = headers_for(owner)

    def found(q):
        return [item["id"] for item in client.get("/api/v1/users", headers=headers, params={"q": q}).json()["items"]]

    assert found("chidi") == [str(chidi.id)]
    assert found("OKEKE@") == [str(chidi.id)]


def test_search_treats_percent_and_underscore_literally(client, pharmacy, owner, make_user):
    make_user(pharmacy, full_name="Plain Name")
    underscored = make_user(pharmacy, full_name="Snake_Case")
    headers = headers_for(owner)

    def total(q):
        return client.get("/api/v1/users", headers=headers, params={"q": q}).json()["total"]

    assert total("%") == 0  # not "match everything"
    assert total("_") == 1
    assert client.get("/api/v1/users", headers=headers, params={"q": "_"}).json()["items"][0]["id"] == str(
        underscored.id
    )


# --- Create, get, update -----------------------------------------------------


def test_create_user(client, owner, login):
    response = client.post("/api/v1/users", json=NEW_USER, headers=headers_for(owner))

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "full_name", "role", "is_active", "created_at"}
    assert (body["email"], body["full_name"], body["role"], body["is_active"]) == (
        "bola@example.com",
        "Bola Ade",
        "staff",
        True,
    )
    assert "starting-password" not in response.text
    # The new user can log in with the starting password
    assert login("bola@example.com", "starting-password").status_code == 200


@pytest.mark.parametrize("role", ["owner", "manager", "staff"])
def test_create_user_with_each_role(client, owner, role):
    response = client.post("/api/v1/users", json=NEW_USER | {"role": role}, headers=headers_for(owner))

    assert response.status_code == 201
    assert response.json()["role"] == role


def test_create_user_with_email_used_in_any_pharmacy_is_409(client, owner, other_pharmacy_user):
    headers = headers_for(owner)

    for email in ("ada@example.com", "ZED@other.example.com"):  # own pharmacy, other pharmacy
        response = client.post("/api/v1/users", json=NEW_USER | {"email": email}, headers=headers)
        assert_error(response, 409, "conflict", "Email already registered")


@pytest.mark.parametrize(
    "change",
    [
        {"role": "admin"},
        {"password": "short"},
        {"email": "not-an-email"},
        {"full_name": "  "},
        {"pharmacy_id": "00000000-0000-0000-0000-000000000000"},
        {"is_active": False},
    ],
    ids=["bad-role", "short-password", "bad-email", "blank-name", "pharmacy_id", "unknown-field"],
)
def test_create_user_rejects_invalid_bodies(client, owner, db, change):
    response = client.post("/api/v1/users", json=NEW_USER | change, headers=headers_for(owner))

    assert_error(response, 422, "validation_error")
    assert db.scalar(select(User).where(User.email == "bola@example.com")) is None


def test_get_user(client, owner, staff):
    response = client.get(f"/api/v1/users/{staff.id}", headers=headers_for(owner))

    assert response.status_code == 200
    assert response.json()["email"] == "sam@example.com"
    assert "password" not in response.text


def test_update_full_name_role_and_is_active(client, owner, staff):
    headers = headers_for(owner)

    response = client.patch(
        f"/api/v1/users/{staff.id}",
        json={"full_name": "  Samuel Staff ", "role": "manager", "is_active": False},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["full_name"], body["role"], body["is_active"]) == ("Samuel Staff", "manager", False)


def test_update_changes_only_the_fields_sent(client, owner, staff):
    response = client.patch(f"/api/v1/users/{staff.id}", json={"role": "manager"}, headers=headers_for(owner))

    assert (response.json()["full_name"], response.json()["role"]) == ("Sam Staff", "manager")


@pytest.mark.parametrize(
    "body",
    [{}, {"full_name": None}, {"role": None}, {"is_active": None}, {"email": "new@example.com"}, {"role": "admin"}],
    ids=["empty", "null-name", "null-role", "null-active", "email-not-editable", "bad-role"],
)
def test_update_rejects_invalid_bodies(client, owner, staff, body):
    response = client.patch(f"/api/v1/users/{staff.id}", json=body, headers=headers_for(owner))

    assert_error(response, 422, "validation_error")


def test_deactivated_user_gets_401_on_their_next_request(client, owner, staff):
    staff_headers = headers_for(staff)
    assert client.get("/api/v1/me", headers=staff_headers).status_code == 200

    response = client.patch(f"/api/v1/users/{staff.id}", json={"is_active": False}, headers=headers_for(owner))
    assert response.status_code == 200

    assert_unauthorized(client.get("/api/v1/me", headers=staff_headers))


def test_deactivated_user_can_be_reactivated(client, owner, pharmacy, make_user, login):
    inactive = make_user(pharmacy, is_active=False, email="back@example.com")
    assert login("back@example.com", DEFAULT_PASSWORD).status_code == 401

    response = client.patch(f"/api/v1/users/{inactive.id}", json={"is_active": True}, headers=headers_for(owner))

    assert response.json()["is_active"] is True
    assert login("back@example.com", DEFAULT_PASSWORD).status_code == 200


# --- Last active owner -------------------------------------------------------

LAST_OWNER_CHANGES = [{"role": "manager"}, {"role": "staff"}, {"is_active": False}]
LAST_OWNER_IDS = ["to-manager", "to-staff", "deactivate"]


@pytest.mark.parametrize("change", LAST_OWNER_CHANGES, ids=LAST_OWNER_IDS)
def test_last_active_owner_cant_demote_or_deactivate_themselves(client, owner, db, change):
    response = client.patch(f"/api/v1/users/{owner.id}", json=change, headers=headers_for(owner))

    error = assert_error(response, 409, "conflict")
    assert "last active owner" in error["message"]
    db.expire_all()
    still = db.get(User, owner.id)
    assert (still.role, still.is_active) == ("owner", True)


@pytest.mark.parametrize("change", LAST_OWNER_CHANGES, ids=LAST_OWNER_IDS)
def test_an_inactive_second_owner_doesnt_count(client, pharmacy, owner, make_user, change):
    make_user(pharmacy, role=Role.OWNER, is_active=False)

    response = client.patch(f"/api/v1/users/{owner.id}", json=change, headers=headers_for(owner))

    assert_error(response, 409, "conflict")


@pytest.mark.parametrize("change", LAST_OWNER_CHANGES, ids=LAST_OWNER_IDS)
def test_with_a_second_active_owner_an_owner_can_be_demoted_or_deactivated(client, pharmacy, owner, make_user, change):
    second = make_user(pharmacy, role=Role.OWNER)

    # By themselves...
    response = client.patch(f"/api/v1/users/{owner.id}", json=change, headers=headers_for(owner))
    assert response.status_code == 200, response.text

    # ...and then the second owner is the last one, so they're protected
    response = client.patch(f"/api/v1/users/{second.id}", json=change, headers=headers_for(second))
    assert_error(response, 409, "conflict")


def test_one_owner_can_demote_another(client, pharmacy, owner, make_user):
    second = make_user(pharmacy, role=Role.OWNER)

    response = client.patch(f"/api/v1/users/{second.id}", json={"role": "staff"}, headers=headers_for(owner))

    assert response.json()["role"] == "staff"


def test_last_owner_can_still_change_their_name(client, owner):
    response = client.patch(
        f"/api/v1/users/{owner.id}", json={"full_name": "Ada Renamed", "role": "owner"}, headers=headers_for(owner)
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Ada Renamed"


def test_owners_in_another_pharmacy_dont_count(client, owner, make_pharmacy, make_user):
    make_user(make_pharmacy("Other Pharmacy"), role=Role.OWNER)

    response = client.patch(f"/api/v1/users/{owner.id}", json={"role": "staff"}, headers=headers_for(owner))

    assert_error(response, 409, "conflict")
