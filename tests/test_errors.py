"""Every error, from every kind of failure, has the same shape:
{"error": {"code": "...", "message": "...", "details": [...]}}"""

import logging

from fastapi.routing import APIRoute
from sqlalchemy.exc import OperationalError

from app.dependencies import get_db
from app.main import app
from app.models import Role
from tests.helpers import assert_error, assert_unauthorized, headers_for

# A recognisable value to send as a password. Over 128 characters, so it fails
# validation; the test checks it never comes back in the error.
ECHO_MARKER = "do-not-echo-this-value-" + "x" * 120


def test_401_not_authenticated(client):
    assert_unauthorized(client.get("/api/v1/me"))


def test_403_forbidden(client, make_pharmacy, make_user):
    staff = make_user(make_pharmacy(), role=Role.STAFF)

    error = assert_error(client.get("/api/v1/users", headers=headers_for(staff)), 403, "forbidden")
    assert error["details"] == []


def test_404_unknown_route(client):
    assert_error(client.get("/api/v1/no-such-thing"), 404, "not_found", "Not found")
    assert_error(client.get("/not-even-the-api"), 404, "not_found")


def test_404_missing_record(client, make_pharmacy, make_user):
    owner = make_user(make_pharmacy(), role=Role.OWNER)

    response = client.get("/api/v1/users/00000000-0000-0000-0000-000000000000", headers=headers_for(owner))

    assert_error(response, 404, "not_found", "User not found")


def test_405_method_not_allowed(client):
    # Users are never deleted, so there's no DELETE route
    response = client.delete("/api/v1/me")

    assert_error(response, 405, "method_not_allowed")
    assert "GET" in response.headers["Allow"]


def test_409_conflict(register):
    register(email="ada@example.com")

    assert_error(register(email="ada@example.com"), 409, "conflict", "Email already registered")


def test_400_bad_request(client, auth_headers):
    headers = auth_headers()
    body = {"current_password": "wrong-password", "new_password": "a-new-password"}

    assert_error(client.patch("/api/v1/me/password", headers=headers, json=body), 400, "bad_request")


def test_422_lists_each_problem_with_its_location(register):
    response = register(email="not-an-email", password="short", pharmacy_name="   ")

    error = assert_error(response, 422, "validation_error")
    problems = {(d["location"], d["field"]) for d in error["details"]}
    assert problems == {("body", "email"), ("body", "password"), ("body", "pharmacy_name")}
    assert all(set(d) == {"location", "field", "message"} and d["message"] for d in error["details"])


def test_422_never_echoes_passwords_or_other_values(client, register, auth_headers):
    responses = [
        register(password=ECHO_MARKER),
        client.post("/api/v1/auth/login", json={"email": "ada@example.com", "password": ECHO_MARKER}),
        register(email="marker-not-an-email"),
    ]
    headers = auth_headers()
    responses.append(
        client.patch(
            "/api/v1/me/password",
            headers=headers,
            json={"current_password": ECHO_MARKER, "new_password": ECHO_MARKER},
        )
    )

    for response in responses:
        assert_error(response, 422, "validation_error")
        assert "do-not-echo-this-value" not in response.text
        assert "marker-not-an-email" not in response.text
        assert '"input"' not in response.text


def test_422_for_bad_query_and_path_values(client, make_pharmacy, make_user):
    headers = headers_for(make_user(make_pharmacy(), role=Role.OWNER))

    error = assert_error(client.get("/api/v1/users?limit=abc", headers=headers), 422, "validation_error")
    assert error["details"][0]["location"] == "query"
    assert error["details"][0]["field"] == "limit"

    error = assert_error(client.get("/api/v1/users/not-a-uuid", headers=headers), 422, "validation_error")
    assert (error["details"][0]["location"], error["details"][0]["field"]) == ("path", "user_id")
    assert "not-a-uuid" not in client.get("/api/v1/users/not-a-uuid", headers=headers).text


def test_422_for_body_that_is_not_json(client):
    response = client.post("/api/v1/auth/login", content="{not json", headers={"Content-Type": "application/json"})

    assert_error(response, 422, "validation_error")


def test_500_is_generic_and_the_real_error_is_logged(quiet_client, caplog):
    class ExplodingSession:
        def execute(self, *args, **kwargs):
            # Not a database error, so the health check doesn't catch it
            raise RuntimeError("internal detail: connection string postgres://secret@db")

    app.dependency_overrides[get_db] = lambda: ExplodingSession()

    with caplog.at_level(logging.ERROR):
        response = quiet_client.get("/api/v1/health")

    error = assert_error(response, 500, "internal_error")
    assert error["details"] == []
    assert "internal detail" not in response.text
    assert "secret" not in response.text
    # The server log has the real error
    assert "internal detail" in caplog.text


def test_503_uses_the_same_shape(client):
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    app.dependency_overrides[get_db] = lambda: BrokenSession()

    assert_error(client.get("/api/v1/health"), 503, "service_unavailable")


def test_docs_describe_errors_with_the_shared_shape():
    spec = app.openapi()
    for route in app.routes:
        if isinstance(route, APIRoute) and route.include_in_schema:
            for method in route.methods:
                responses = spec["paths"][route.path_format][method.lower()]["responses"]
                if "422" in responses:
                    schema = responses["422"]["content"]["application/json"]["schema"]
                    assert schema["$ref"].endswith("/ErrorResponse"), f"{method} {route.path}"
