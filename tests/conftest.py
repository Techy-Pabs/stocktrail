"""Shared test fixtures.

Tests use their own database (the development database name + "_test").
Its tables are built by running the real Alembic migrations, so the tests
check the same schema (constraints included) that production gets. Every
table is emptied before each test.
"""

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.dependencies import get_db
from app.main import app

DEV_DATABASE_URL = make_url(settings.database_url)
TEST_DATABASE_URL = DEV_DATABASE_URL.set(database=f"{DEV_DATABASE_URL.database}_test")
assert TEST_DATABASE_URL.database != DEV_DATABASE_URL.database

DEFAULT_PASSWORD = "correct-horse-battery"


def _create_test_database_if_missing() -> None:
    # Connect to PostgreSQL's built-in "postgres" database to create ours
    admin_engine = create_engine(DEV_DATABASE_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DATABASE_URL.database},
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DATABASE_URL.database}"'))
    admin_engine.dispose()


def alembic_config() -> Config:
    """Alembic settings pointing at the test database, never the real one."""
    config = Config("alembic.ini")
    url = TEST_DATABASE_URL.render_as_string(hide_password=False)
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def engine():
    """Create the test database and migrate it once per test run."""
    _create_test_database_if_missing()
    engine = create_engine(TEST_DATABASE_URL)
    # Start from nothing, so a schema left over from an older run can't hide a migration bug
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(), "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine):
    """Empty every table before each test, so each test starts clean."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users, pharmacies CASCADE"))
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(session_factory):
    """A database session for tests to check what was saved."""
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def client(session_factory):
    """A TestClient whose requests use the test database."""

    def get_test_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = get_test_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def register(client):
    """register(email=..., ...) -> the response from POST /api/v1/auth/register."""

    def _register(
        email="ada@example.com",
        password=DEFAULT_PASSWORD,
        pharmacy_name="Ada Pharmacy",
        full_name="Ada Obi",
        **extra,
    ):
        body = {"pharmacy_name": pharmacy_name, "full_name": full_name, "email": email, "password": password}
        return client.post("/api/v1/auth/register", json=body | extra)

    return _register


@pytest.fixture
def login(client):
    """login(email, password) -> the response from POST /api/v1/auth/login."""

    def _login(email="ada@example.com", password=DEFAULT_PASSWORD):
        return client.post("/api/v1/auth/login", json={"email": email, "password": password})

    return _login


@pytest.fixture
def auth_headers(register, login):
    """auth_headers(email, password) -> registers and logs in, returns the Bearer header."""

    def _auth_headers(email="ada@example.com", password=DEFAULT_PASSWORD):
        assert register(email=email, password=password).status_code == 201
        response = login(email, password)
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _auth_headers
