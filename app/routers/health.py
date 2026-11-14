import logging

from fastapi import APIRouter, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import ErrorResponse, error_response
from app.dependencies import DbSession
from app.docs import examples

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

DATABASE_UNREACHABLE = "The API is running but cannot reach its database"


@router.get(
    "/health",
    responses={
        200: examples.response("Running, and the database is reachable", examples.HEALTH),
        503: examples.response(
            DATABASE_UNREACHABLE,
            {
                "error": {
                    "code": "service_unavailable",
                    "message": DATABASE_UNREACHABLE,
                    "details": [{"component": "database", "status": "unreachable"}],
                }
            },
            ErrorResponse,
        ),
    },
)
def health(db: DbSession):
    """Whether the API is up and can reach its database.

    503 (in the shared error format) when the database is unreachable, so a
    host or load balancer can tell the API isn't really working.
    """
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # Only the error type is logged: the message can contain the database address
        logger.warning("Health check: database unreachable (%s)", type(exc).__name__)
        return error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            DATABASE_UNREACHABLE,
            details=[{"component": "database", "status": "unreachable"}],
        )
    return {"status": "ok", "database": "ok"}
