import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import Pharmacy, User
from app.services import registration
from tests.helpers import assert_error


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_register_creates_pharmacy_and_owner(register, db):
    response = register(email="Ada@Example.com", pharmacy_name="  Ada Pharmacy ", full_name="Ada Obi")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"user", "pharmacy"}
    assert set(body["user"]) == {"id", "email", "full_name", "role", "is_active", "created_at"}
    assert set(body["pharmacy"]) == {"id", "name", "address", "created_at"}
    assert body["user"]["email"] == "ada@example.com"  # stored lowercase
    assert body["user"]["role"] == "owner"
    assert body["user"]["is_active"] is True
    assert body["pharmacy"]["name"] == "Ada Pharmacy"  # surrounding spaces removed

    user = db.scalar(select(User))
    pharmacy = db.scalar(select(Pharmacy))
    assert (count(db, User), count(db, Pharmacy)) == (1, 1)
    assert str(user.id) == body["user"]["id"]
    assert str(pharmacy.id) == body["pharmacy"]["id"]
    assert user.pharmacy_id == pharmacy.id


def test_register_response_contains_no_password_data(register):
    response = register(password="correct-horse-battery")

    assert "password" not in response.text
    assert "argon2" not in response.text
    assert "correct-horse-battery" not in response.text


def test_password_is_stored_as_argon2_hash(register, db):
    register(password="correct-horse-battery")

    user = db.scalar(select(User))
    assert user.password_hash.startswith("$argon2")
    assert "correct-horse-battery" not in user.password_hash


def test_register_rolls_back_pharmacy_if_user_insert_fails(quiet_client, db, monkeypatch, caplog):
    # Make the database reject the user row: password_hash is NOT NULL.
    # The pharmacy row is inserted first, in the same transaction.
    monkeypatch.setattr(registration, "hash_password", lambda password: None)
    body = {"pharmacy_name": "Ada Pharmacy", "full_name": "Ada Obi", "email": "ada@example.com", "password": "x" * 8}

    response = quiet_client.post("/api/v1/auth/register", json=body)

    # The client gets a generic 500; the real database error is only in the server log
    assert_error(response, 500, "internal_error")
    assert "password_hash" not in response.text
    assert any(isinstance(r.exc_info[1], IntegrityError) for r in caplog.records if r.exc_info)

    assert count(db, User) == 0
    assert count(db, Pharmacy) == 0  # rolled back with the user


def test_register_duplicate_email_returns_409(register, db):
    assert register(email="ada@example.com").status_code == 201

    response = register(email="ADA@example.com", pharmacy_name="Another Pharmacy")  # same email, other case

    assert response.status_code == 409
    assert_error(response, 409, "conflict", "Email already registered")
    # The second pharmacy wasn't created either
    assert (count(db, User), count(db, Pharmacy)) == (1, 1)


def test_register_duplicate_email_race_returns_409(register, db, monkeypatch):
    # Two sign-ups at the same moment: both pass the "email taken?" check,
    # and the database's unique constraint stops the second
    assert register(email="ada@example.com").status_code == 201
    monkeypatch.setattr(registration, "email_taken", lambda db, email: False)

    response = register(email="ada@example.com", pharmacy_name="Another Pharmacy")

    assert response.status_code == 409
    assert (count(db, User), count(db, Pharmacy)) == (1, 1)


def test_register_rejects_pharmacy_id_in_body(register, db):
    response = register(pharmacy_id=str(uuid.uuid4()))

    assert response.status_code == 422
    assert (count(db, User), count(db, Pharmacy)) == (0, 0)


def test_register_rejects_role_in_body(register, db):
    # A new sign-up is always the owner of a new pharmacy; the role isn't chosen by the client
    response = register(role="manager")

    assert response.status_code == 422
    assert count(db, User) == 0


@pytest.mark.parametrize("password", ["short7!", "x" * 129])
def test_register_password_rules(register, password):
    response = register(password=password)

    assert response.status_code == 422
    assert password not in response.text  # the password isn't echoed back


@pytest.mark.parametrize("field", ["pharmacy_name", "full_name"])
def test_register_rejects_blank_names(register, field):
    assert register(**{field: "   "}).status_code == 422


def test_register_rejects_invalid_email(register):
    assert register(email="not-an-email").status_code == 422
