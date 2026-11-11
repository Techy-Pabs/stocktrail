import logging

from fastapi import APIRouter, FastAPI
from fastapi.responses import RedirectResponse

from app.core.errors import ErrorResponse, install_error_handlers
from app.routers import auth, health, me, users

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")

API_PREFIX = "/api/v1"

app = FastAPI(
    title="Stocktrail",
    description="Inventory API for community pharmacies: batches, expiry dates and first expired, first out selling.",
    version="0.2.0",
)

# Every error, from every route, as {"error": {"code", "message", "details"}}
install_error_handlers(app)

# Every route lives under /api/v1. Declaring 422 here makes the docs show the
# shared error shape instead of FastAPI's default validation error.
api = APIRouter(
    prefix=API_PREFIX,
    responses={422: {"model": ErrorResponse, "description": "Invalid request (see error.details)"}},
)
api.include_router(health.router)
api.include_router(auth.router)
api.include_router(me.router)
api.include_router(users.router)
app.include_router(api)


# Visiting the base URL opens the Swagger page. Hidden from the docs themselves.
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")
