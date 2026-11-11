import pytest
from pydantic import ValidationError

from app.core.config import Settings

SECRET = "s" * 40


@pytest.mark.parametrize(
    "given, expected",
    [
        ("postgresql://u:pw@host/db?sslmode=require", "postgresql+psycopg://u:pw@host/db?sslmode=require"),
        ("postgres://u:pw@host:5432/db", "postgresql+psycopg://u:pw@host:5432/db"),
        ("postgresql+psycopg://u:pw@db:5432/db", "postgresql+psycopg://u:pw@db:5432/db"),
    ],
)
def test_database_url_uses_psycopg_driver(given, expected):
    assert Settings(_env_file=None, database_url=given, jwt_secret_key=SECRET).database_url == expected


def test_empty_database_url_is_rejected_clearly():
    with pytest.raises(ValidationError, match="DATABASE_URL is empty"):
        Settings(_env_file=None, database_url="  ", jwt_secret_key=SECRET)


def test_short_jwt_secret_is_rejected_without_showing_it():
    secret = "change-me"

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_url="postgresql://u:p@h/db", jwt_secret_key=secret)

    message = str(error.value)
    assert "jwt_secret_key" in message  # the error still names the setting
    assert secret not in message
    assert "input_value" not in message
