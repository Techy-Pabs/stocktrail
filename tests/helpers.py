"""Small helpers shared by the tests."""

from app.core.security import create_access_token

UNAUTHORIZED_MESSAGE = "Could not validate credentials"


def assert_error(response, status_code: int, code: str, message: str | None = None) -> dict:
    """Check a response is an error in the shared format; returns the "error" part."""
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) == {"code", "message", "details"}
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["details"], list)
    if message is not None:
        assert error["message"] == message
    return error


def assert_unauthorized(response) -> None:
    """The one 401 sent for every token failure."""
    assert_error(response, 401, "not_authenticated", UNAUTHORIZED_MESSAGE)
    assert response.headers["WWW-Authenticate"] == "Bearer"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def headers_for(user) -> dict[str, str]:
    """A valid Bearer header for this user, as if they had just logged in."""
    return bearer(create_access_token(user.id, user.token_version))
