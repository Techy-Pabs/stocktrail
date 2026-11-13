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
docker compose up --build   # API on http://localhost:8002, Swagger at /docs
```

The database is on `localhost:5434` from your machine. Both ports are chosen
so ShopAssist (API 8000, database 5432) and Pinpage (API 8001, database 5433)
can run at the same time.

## Tests and lint

```sh
docker compose run --rm --build tests                       # full test suite
docker compose run --rm --build tests ruff check .          # lint
docker compose run --rm --build tests ruff format --check . # formatting
```

The tests use a separate `stocktrail_test` database, built by running the real
migrations.

## Roles

Every user belongs to one pharmacy and has one role. The role is read from the
database on every request (never from the login token), so a change takes
effect on the user's next request.

| Role | Can do |
| --- | --- |
| `owner` | Everything, including managing the pharmacy's users (`/users`) |
| `manager` | Their own account (`/me`); more permissions come with later slices |
| `staff` | Their own account (`/me`); more permissions come with later slices |

A pharmacy always keeps at least one active owner: the last one can't be
demoted or deactivated (409). Users are never deleted, only deactivated, and a
deactivated user is logged out on their next request. An owner can reset any
other user's password, including another owner's, but changes their own only
through `/me/password` with their current password.

## Endpoints

All routes are under `/api/v1`. Log in, then paste the token into **Authorize**
in Swagger (`/docs`).

| Method | Path | Who | What it does |
| --- | --- | --- | --- |
| GET | `/health` | anyone | API status and whether the database is reachable (503 if not) |
| POST | `/auth/register` | anyone | Creates a pharmacy and its owner together |
| POST | `/auth/login` | anyone | Returns a JWT |
| GET | `/me` | logged in | The logged in user and their pharmacy |
| PATCH | `/me/password` | logged in | Change your password (needs the current one). Returns a new token; every older token stops working |
| GET | `/users` | owner | The pharmacy's users, paged. Filters: `role`, `is_active`, `q` (name or email). Sort: `full_name`, `email`, `created_at` |
| POST | `/users` | owner | Add a user (email, full name, role, starting password) |
| GET | `/users/{id}` | owner | One user |
| PATCH | `/users/{id}` | owner | Change full name, role or active flag |
| POST | `/users/{id}/reset-password` | owner | Set a new starting password for another user; their old tokens stop working. Your own id is a 400: use `/me/password` |

A user from another pharmacy is always a 404, never a 403. No endpoint accepts
a `pharmacy_id`: it always comes from the logged in user.

## Errors

Every error, from every endpoint, has the same shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "The request contains invalid data",
    "details": [
      {"location": "body", "field": "password", "message": "String should have at least 8 characters"}
    ]
  }
}
```

| Status | `code` |
| --- | --- |
| 400 | `bad_request` |
| 401 | `not_authenticated` |
| 403 | `forbidden` |
| 404 | `not_found` |
| 405 | `method_not_allowed` |
| 409 | `conflict` |
| 422 | `validation_error` (`details` lists each problem; submitted values are never echoed) |
| 500 | `internal_error` (generic message; the real error is only in the server log) |
| 503 | `service_unavailable` (health check: database unreachable) |

## Paging and sorting

List endpoints take `limit` (1 to 100, default 20), `offset` (0 or more,
default 0) and `sort` (one of the endpoint's sort fields; a leading `-` sorts
descending). Values out of range, or an unknown sort field, are a 422. Rows
with equal sort values are ordered by id, so pages never skip or repeat a row.

`GET /api/v1/users?limit=2&offset=0&sort=-created_at`

```json
{
  "items": [
    {"id": "…", "email": "sam@example.com", "full_name": "Sam Staff", "role": "staff", "is_active": true, "created_at": "2026-11-11T10:05:00Z"},
    {"id": "…", "email": "ada@example.com", "full_name": "Ada Obi", "role": "owner", "is_active": true, "created_at": "2026-11-10T09:00:00Z"}
  ],
  "total": 5,
  "limit": 2,
  "offset": 0
}
```

`total` counts every matching row, not just this page.
