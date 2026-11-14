# Stocktrail

Stocktrail is an inventory API for Nigerian community pharmacies. It keeps
each pharmacy's product catalogue and, as the next milestones land, its stock
in batches with expiry dates, so the batch that expires first is always sold
first (FEFO: first expired, first out).

It is built for pharmacy owners, managers and counter staff, and for the apps
and point-of-sale systems they use. There is no frontend yet: the API and its
Swagger docs (`/docs`) are the product.

Every pharmacy is a tenant. Every user belongs to exactly one pharmacy, and
the API always takes the pharmacy from the logged in user, never from the
request, so a pharmacy only ever sees its own data.

## Features so far (Milestone 1)

- **Pharmacies and accounts.** Registering creates a pharmacy and its owner in
  one step. Log in with email and password to get a token (JWT).
- **Users and roles.** Owners add users as owner, manager or staff, change
  their roles, deactivate them and reset their passwords.
- **Product catalogue.** Products with name, generic name, strength, form,
  barcode, reorder level and selling price, with search, filters, sorting and
  paging. Products are archived, never deleted.
- **Barcodes.** EAN-13, UPC-A and EAN-8, with the check digit verified, and
  lookup by scanning.
- **Security.** Argon2 password hashing, the same 401 for every login or token
  failure, tokens that stop working after a password change, and strict
  separation between pharmacies.
- **Conventions.** One error format and one paging format for every endpoint,
  and Swagger docs with examples on every endpoint.

## Quick start

Needs Docker.

```sh
git config core.hooksPath .githooks   # once per clone: turns on the commit message guard
cp .env.example .env                  # then replace the placeholder values
docker compose up --build             # API on http://localhost:8002, Swagger at /docs
```

The database is on `localhost:5434` from your machine. Both ports are chosen
so ShopAssist (API 8000, database 5432) and Pinpage (API 8001, database 5433)
can run at the same time.

## A short walkthrough with curl

With the API running, register a pharmacy, log in, add a product and find it
by its barcode. (The barcodes in this README and in the docs are made up.)

```sh
BASE=http://localhost:8002/api/v1

# 1. Register a pharmacy and its owner
curl -s -X POST "$BASE/auth/register" -H "Content-Type: application/json" \
  -d '{"pharmacy_name": "Yaba Community Pharmacy", "full_name": "Adaeze Okafor",
       "email": "adaeze@example.com", "password": "a-long-passphrase"}'

# 2. Log in and keep the token
TOKEN=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" \
  -d '{"email": "adaeze@example.com", "password": "a-long-passphrase"}' \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])')

# 3. Add a product (the price is in kobo: 50000 kobo is 500 naira)
curl -s -X POST "$BASE/products" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Paracetamol 500 mg Tablets", "generic_name": "Paracetamol", "strength": "500 mg",
       "form": "tablet", "barcode": "6150000000013", "reorder_level": 20, "selling_price_kobo": 50000}'

# 4. Look it up by scanning its barcode
curl -s "$BASE/products/barcode/6150000000013" -H "Authorization: Bearer $TOKEN"
```

Step 4 returns the product:

```json
{
  "id": "…",
  "name": "Paracetamol 500 mg Tablets",
  "generic_name": "Paracetamol",
  "strength": "500 mg",
  "form": "tablet",
  "barcode": "6150000000013",
  "reorder_level": 20,
  "selling_price_kobo": 50000,
  "is_active": true,
  "created_at": "2026-11-14T09:30:00Z",
  "updated_at": "2026-11-14T09:30:00Z"
}
```

## Endpoints

All routes are under `/api/v1`. In Swagger (`/docs`), log in, then paste the
token into **Authorize**.

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
| GET | `/products` | everyone | The pharmacy's products, paged. Filters: `q` (name or generic name), `form`, `is_active`. Sort: `name`, `created_at`, `selling_price_kobo` |
| GET | `/products/{id}` | everyone | One product, archived or not |
| GET | `/products/barcode/{code}` | everyone | Find a product by barcode, archived included |
| POST | `/products` | owner, manager | Add a product |
| PATCH | `/products/{id}` | owner, manager | Change any field; `is_active: false` archives, `true` restores |

A user or product from another pharmacy is always a 404, never a 403. No
endpoint accepts a `pharmacy_id`. Products and users are never deleted, so
there is no DELETE route.

## Roles

Every user has one role. The role is read from the database on every request
(never from the login token), so a change takes effect on the user's next
request.

| Role | Can do |
| --- | --- |
| `owner` | Everything, including managing the pharmacy's users (`/users`) |
| `manager` | Their own account, and adding and changing products |
| `staff` | Their own account, and listing, reading and looking up products |

A pharmacy always keeps at least one active owner: the last one can't be
demoted or deactivated (409). Users are never deleted, only deactivated, and a
deactivated user is logged out on their next request. An owner can reset any
other user's password, including another owner's, but changes their own only
through `/me/password` with their current password.

## Money

Money is always a whole number of **kobo** (100 kobo is 1 naira), never a
decimal. `selling_price_kobo: 185000` is 1,850 naira. A price sent as a
decimal, a string or a negative number is a 422.

## Barcodes

A barcode is checked the same way when a product is saved and when it is
looked up:

1. Spaces are removed (also tabs and newlines a scanner may add).
2. Only the digits 0 to 9 are allowed.
3. It must be 13 digits (EAN-13), 12 (UPC-A) or 8 (EAN-8).
4. The last digit, the check digit, must match the others. If it doesn't, the
   error says what it should be, to help spot a typo:
   `The check digit (the last digit) is wrong: it should be 3, not 4.`

**UPC-A is stored as EAN-13.** A 12 digit UPC-A is the same product as the 13
digit EAN-13 made by putting a 0 in front of it, so Stocktrail stores it that
way: `615000000013` is saved as `0615000000013`. Scanning either form finds
the product, and the two count as the same barcode.

**How the check digit works.** Starting from the right-hand end of the digits
(without the check digit), multiply them by 3, 1, 3, 1 and so on, and add the
results. The check digit is what brings that total up to the next multiple of
10. For `615000000001` the total is 17, so the check digit is 3 and the full
barcode is `6150000000013`. The code, with a worked example, is in
[app/core/barcodes.py](app/core/barcodes.py).

A barcode is unique within a pharmacy (a duplicate is a 409), but two
pharmacies can stock the same product with the same barcode.

## Errors

Every error, from every endpoint, has the same shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "The request contains invalid data",
    "details": [
      {"location": "body", "field": "barcode", "message": "The check digit (the last digit) is wrong: it should be 3, not 4. Check the barcode for a mistyped or swapped digit."}
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

`GET /api/v1/products?limit=2&offset=0&sort=-selling_price_kobo`

```json
{
  "items": [
    {"id": "…", "name": "Amoxicillin 250 mg/5 ml Suspension, 100 ml", "selling_price_kobo": 185000, "…": "…"},
    {"id": "…", "name": "Paracetamol 500 mg Tablets", "selling_price_kobo": 50000, "…": "…"}
  ],
  "total": 2,
  "limit": 2,
  "offset": 0
}
```

`total` counts every matching row, not just this page.

## Tests and lint

```sh
docker compose run --rm --build tests                       # full test suite
docker compose run --rm --build tests ruff check .          # lint
docker compose run --rm --build tests ruff format --check . # formatting
```

The tests use a separate `stocktrail_test` database, built by running the real
migrations. CI runs lint, the migrations, the tests, a commit message check and
a gitleaks secret scan on every pull request and every push to `main`.

## Roadmap

| Milestone | What it adds |
| --- | --- |
| 1. Foundation (done) | Accounts, roles, users, the product catalogue and barcodes |
| 2. Stock in | Receiving stock in batches, each with a batch number, expiry date and cost price |
| 3. Stock out with FEFO | Selling and dispensing, always taking from the batch that expires first |
| 4. Expiry and adjustments | Expiry alerts, writing off expired or damaged stock, and stock counts |
| 5. Reports and hardening | Stock value, sales and reorder reports, rate limiting and audit logs |
| 6. Demo and launch | A demo pharmacy, deployment and launch |
