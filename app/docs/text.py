"""The API description and tag descriptions shown at the top of /docs."""

API_DESCRIPTION = """
**Stocktrail** is an inventory API for Nigerian community pharmacies.

It keeps each pharmacy's product catalogue, and (from the next milestones) its
stock in batches with expiry dates, so the batch that expires first is sold
first. It is built for pharmacy owners, managers and counter staff, and for
the apps and point-of-sale systems they use.

**Getting started**

1. `POST /api/v1/auth/register` creates your pharmacy and its owner account.
2. `POST /api/v1/auth/login` returns a token. Click **Authorize** above and paste it in.
3. Add products with `POST /api/v1/products`, and find them by scanning a barcode
   with `GET /api/v1/products/barcode/{code}`.

**Conventions**

- Every pharmacy only ever sees its own data. The pharmacy always comes from
  the logged in user, never from the request.
- Money is always whole **kobo** (100 kobo = 1 naira), never a decimal.
- Lists take `limit`, `offset` and `sort`, and return `items` and `total`.
- Every error has the same shape: `{"error": {"code", "message", "details"}}`.
"""

TAGS = [
    {
        "name": "auth",
        "description": "Register a pharmacy with its owner, and log in to get a token.",
    },
    {
        "name": "me",
        "description": "The logged in user: their details, pharmacy and password.",
    },
    {
        "name": "users",
        "description": "**Owners only.** Add, list, update and deactivate the pharmacy's users, "
        "and reset other users' passwords. Users are never deleted, and the last active owner "
        "can't be demoted or deactivated.",
    },
    {
        "name": "products",
        "description": "The pharmacy's product catalogue. Everyone can list, read and look up "
        "products by barcode; **owners and managers** can add and change them. Products are "
        "archived (`is_active: false`), never deleted. Barcodes are EAN-13, UPC-A or EAN-8 with a "
        "valid check digit; a UPC-A is stored as the EAN-13 it equals (a leading 0 added).",
    },
    {
        "name": "health",
        "description": "Whether the API is running and can reach its database.",
    },
]
