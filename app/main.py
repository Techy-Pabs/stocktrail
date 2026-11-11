import logging

from fastapi import APIRouter, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

from app.routers import auth, health, me

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")

API_PREFIX = "/api/v1"

app = FastAPI(
    title="Stocktrail",
    description="Inventory API for community pharmacies: batches, expiry dates and first expired, first out selling.",
    version="0.1.0",
)


@app.exception_handler(RequestValidationError)
def validation_error_handler(request: Request, exc: RequestValidationError):
    # FastAPI's default 422 response echoes back the invalid value, which
    # could be a password. Send the error details without the "input".
    errors = [{k: v for k, v in e.items() if k != "input"} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


# Every route lives under /api/v1
api = APIRouter(prefix=API_PREFIX)
api.include_router(health.router)
api.include_router(auth.router)
api.include_router(me.router)
app.include_router(api)


# Visiting the base URL opens the Swagger page. Hidden from the docs themselves.
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")
