from sqlalchemy import select, update

from app.core import security
from app.models import User
from app.routers import auth
from tests.helpers import assert_error


def test_login_succeeds(register, login):
    register(email="ada@example.com", password="correct-horse-battery")

    response = login("ADA@example.com", "correct-horse-battery")  # email case doesn't matter

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert security.decode_access_token(body["access_token"])


def test_login_email_is_case_insensitive(register, login):
    assert register(email="ada@example.com", password="correct-horse-battery").status_code == 201

    response = login("ADA@EXAMPLE.COM", "correct-horse-battery")

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert security.decode_access_token(body["access_token"])


def test_wrong_password_and_unknown_email_return_identical_401(register, login):
    register(email="ada@example.com", password="correct-horse-battery")

    wrong_password = login("ada@example.com", "wrong-password")
    unknown_email = login("nobody@example.com", "wrong-password")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert_error(wrong_password, 401, "not_authenticated", "Incorrect email or password")
    assert wrong_password.headers["WWW-Authenticate"] == unknown_email.headers["WWW-Authenticate"]


def test_unknown_email_still_checks_a_password_hash(login, monkeypatch):
    # Timing protection: an unknown email does the same slow Argon2 work
    # as a wrong password, so response times don't reveal which emails exist
    checked = []

    def spy(password, hashed):
        checked.append(hashed)
        return False

    monkeypatch.setattr(auth, "verify_password", spy)

    assert login("nobody@example.com", "whatever").status_code == 401
    assert checked == [security.DUMMY_HASH]


def test_inactive_user_cannot_log_in(register, login, db, monkeypatch):
    register(email="ada@example.com", password="correct-horse-battery")
    db.execute(update(User).values(is_active=False))
    db.commit()
    wrong_password = login("ada@example.com", "wrong-password")
    checked = []
    real_verify = auth.verify_password
    monkeypatch.setattr(auth, "verify_password", lambda p, h: checked.append(h) or real_verify(p, h))

    response = login("ada@example.com", "correct-horse-battery")

    # Same 401 as a wrong password, even with the right one
    assert response.status_code == 401
    assert response.json() == wrong_password.json()
    # The password was still checked, so an inactive account takes as long as any other
    assert checked == [db.scalar(select(User.password_hash))]
