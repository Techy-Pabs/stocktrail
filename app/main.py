import logging

from fastapi import APIRouter, FastAPI
from fastapi.responses import RedirectResponse

from app.core.errors import ErrorResponse, install_error_handlers
from app.docs import examples
from app.docs.text import API_DESCRIPTION, TAGS
from app.routers import auth, health, me, products, users

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")

API_PREFIX = "/api/v1"

app = FastAPI(
    title="Stocktrail",
    summary="Inventory API for Nigerian community pharmacies",
    description=API_DESCRIPTION,
    version="0.3.0",
    openapi_tags=TAGS,
)

# Every error, from every route, as {"error": {"code", "message", "details"}}
install_error_handlers(app)

# Every route lives under /api/v1. Declaring 422 here makes the docs show the
# shared error shape instead of FastAPI's default validation error.
api = APIRouter(
    prefix=API_PREFIX,
    responses={422: examples.response("Invalid request (see error.details)", examples.VALIDATION_ERROR, ErrorResponse)},
)
api.include_router(health.router)
api.include_router(auth.router)
api.include_router(me.router)
api.include_router(users.router)
api.include_router(products.router)
app.include_router(api)


# Visiting the base URL opens the Swagger page. Hidden from the docs themselves.
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")
