import pytest
from sqlalchemy import select

from app.models import User

OLD = "correct-horse-battery"
NEW = "a-brand-new-password"


def change_password(client, headers, current, new):
    return client.patch("/api/v1/me/password", headers=headers, json={"current_password": current, "new_password": new})


def test_change_password_works_and_old_password_stops_working(client, auth_headers, login):
    headers = auth_headers(password=OLD)

    response = change_password(client, headers, OLD, NEW)

    assert response.status_code == 204
    assert response.content == b""
    assert login(password=OLD).status_code == 401
    assert login(password=NEW).status_code == 200


def test_wrong_current_password_is_rejected_and_nothing_changes(client, auth_headers, login, db):
    headers = auth_headers(password=OLD)
    hash_before = db.scalar(select(User.password_hash))

    response = change_password(client, headers, "not-my-password", NEW)

    assert response.status_code == 400
    assert response.json() == {"detail": "Current password is incorrect"}
    db.expire_all()
    assert db.scalar(select(User.password_hash)) == hash_before
    assert login(password=OLD).status_code == 200


def test_new_password_must_differ_from_current(client, auth_headers):
    headers = auth_headers(password=OLD)

    assert change_password(client, headers, OLD, OLD).status_code == 400


@pytest.mark.parametrize("new", ["short7!", "x" * 129])
def test_new_password_follows_the_password_rules(client, auth_headers, new):
    headers = auth_headers(password=OLD)

    response = change_password(client, headers, OLD, new)

    assert response.status_code == 422
    assert new not in response.text
    assert OLD not in response.text


def test_change_password_requires_login(client):
    response = client.patch("/api/v1/me/password", json={"current_password": OLD, "new_password": NEW})

    assert response.status_code == 401
