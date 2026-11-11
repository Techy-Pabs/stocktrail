"""Database rules: the migration matches the models, and the database
itself refuses bad data (not only the Python code)."""

import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.models import Role, User
from app.models.user import ROLE_CHECK_SQL
from tests.conftest import alembic_config


def test_migration_matches_models(engine):
    # Same check as "alembic check": nothing in the models is missing from
    # the migration, or different in it
    with engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True, "compare_server_default": True})
        assert compare_metadata(context, Base.metadata) == []


def test_migration_downgrades_and_upgrades_cleanly(engine):
    config = alembic_config()
    command.downgrade(config, "base")
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT to_regclass('users')")) is None
    command.upgrade(config, "head")
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT to_regclass('users')")) == "users"


def test_role_check_lists_every_role():
    for role in Role:
        assert f"'{role.value}'" in ROLE_CHECK_SQL
    assert ROLE_CHECK_SQL.count("'") == 2 * len(Role)


@pytest.fixture
def pharmacy_id(engine, session_factory):
    with engine.begin() as conn:
        return conn.scalar(text("INSERT INTO pharmacies (name) VALUES ('Test Pharmacy') RETURNING id"))


def insert_user(engine, pharmacy_id, **overrides):
    values = {
        "pharmacy_id": pharmacy_id,
        "email": "ada@example.com",
        "full_name": "Ada",
        "password_hash": "x",
        "role": "staff",
    } | overrides
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (pharmacy_id, email, full_name, password_hash, role) "
                "VALUES (:pharmacy_id, :email, :full_name, :password_hash, :role)"
            ),
            values,
        )


@pytest.mark.parametrize("role", ["owner", "manager", "staff"])
def test_database_accepts_valid_roles(engine, pharmacy_id, role):
    insert_user(engine, pharmacy_id, role=role)


@pytest.mark.parametrize("role", ["admin", "OWNER", ""])
def test_database_rejects_invalid_role(engine, pharmacy_id, role):
    # Raw SQL, skipping the Python checks: the CHECK constraint still refuses it
    with pytest.raises(IntegrityError, match="ck_users_role_valid"):
        insert_user(engine, pharmacy_id, role=role)


def test_code_rejects_invalid_role():
    with pytest.raises(ValueError):
        User(role="admin")


def test_database_rejects_uppercase_email(engine, pharmacy_id):
    with pytest.raises(IntegrityError, match="ck_users_email_lowercase"):
        insert_user(engine, pharmacy_id, email="Ada@example.com")


def test_code_lowercases_email():
    assert User(email="  Ada@Example.COM ").email == "ada@example.com"


def test_database_rejects_user_without_pharmacy(engine, pharmacy_id):
    with pytest.raises(IntegrityError, match="fk_users_pharmacy_id_pharmacies"):
        insert_user(engine, uuid.uuid4())


def test_new_users_are_active_by_default(engine, pharmacy_id):
    insert_user(engine, pharmacy_id)
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT is_active FROM users")) is True


def test_pharmacy_with_users_cannot_be_deleted(engine, pharmacy_id):
    insert_user(engine, pharmacy_id)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("DELETE FROM pharmacies"))


def test_database_rejects_blank_pharmacy_name(engine, session_factory):
    with pytest.raises(IntegrityError, match="ck_pharmacies_name_not_blank"), engine.begin() as conn:
        conn.execute(text("INSERT INTO pharmacies (name) VALUES ('   ')"))
