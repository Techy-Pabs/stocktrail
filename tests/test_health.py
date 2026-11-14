from sqlalchemy.exc import OperationalError

from app.dependencies import get_db
from app.main import app
from tests.helpers import assert_error


def test_health_reports_api_and_database_ok(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_unreachable_database(client):
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    app.dependency_overrides[get_db] = lambda: BrokenSession()

    response = client.get("/api/v1/health")

    error = assert_error(response, 503, "service_unavailable")
    assert error["details"] == [{"component": "database", "status": "unreachable"}]
    assert "connection refused" not in response.text


def test_routes_live_under_api_v1(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert paths  # there are routes
    assert all(path.startswith("/api/v1/") for path in paths)


def test_root_redirects_to_docs(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
