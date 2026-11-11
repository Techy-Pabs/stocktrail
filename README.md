# Stocktrail

A multi-tenant inventory API for Nigerian community pharmacies: batches, expiry
dates and first expired, first out (FEFO) selling, built on a general retail core.

Each pharmacy is a tenant. Every user belongs to exactly one pharmacy, and the
API always takes the pharmacy from the logged in user, never from the request.

## Run it locally

Needs Docker.

```sh
git config core.hooksPath .githooks   # once per clone: turns on the commit message guard
cp .env.example .env        # then replace the placeholder values
docker compose up --build   # API on http://localhost:8001, Swagger at /docs
```

The database is on `localhost:5434` from your machine (ShopAssist uses 5432 and
Pinpage 5433, so all three can run at the same time).

## Tests and lint

```sh
docker compose run --rm --build tests                       # full test suite
docker compose run --rm --build tests ruff check .          # lint
docker compose run --rm --build tests ruff format --check . # formatting
```

The tests use a separate `stocktrail_test` database, built by running the real
migrations.

## Endpoints (Slice A)

All routes are under `/api/v1`.

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/health` | API status and whether the database is reachable (503 if not) |
| POST | `/auth/register` | Creates a pharmacy and its owner together |
| POST | `/auth/login` | Returns a JWT. In Swagger, paste it into **Authorize** |
| GET | `/me` | The logged in user and their pharmacy |
| PATCH | `/me/password` | Change password (needs the current one) |
