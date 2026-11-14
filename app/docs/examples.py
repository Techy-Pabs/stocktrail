"""Realistic examples for every endpoint in the Swagger docs.

All barcodes here are made up: they start with 615 (GS1 Nigeria's prefix,
so they look like local products) and have valid check digits.
tests/test_docs.py checks every barcode in the docs is valid.
"""

PHARMACY_ID = "3f2c9a4e-8b1d-4c6a-9e2f-1a7b5c3d9e01"
OWNER_ID = "7a1e4b2c-5d3f-4e8a-b6c9-0d2f1e3a4b5c"
STAFF_ID = "9c3b5d7e-1f2a-4b6c-8d0e-2f4a6b8c0d1e"
PARACETAMOL_ID = "b2d4f6a8-0c1e-4a3b-9d5f-7e9a1c3b5d7f"
AMOXICILLIN_ID = "c4e6a8b0-2d4f-4b5c-8e7a-9b1d3f5a7c9e"
CREATED = "2026-11-14T09:30:00Z"
UPDATED = "2026-11-14T15:45:00Z"
# Shaped like a real token (header.payload.signature) but not a real one
EXAMPLE_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example-payload.example-signature"

# Made-up barcodes with valid check digits
PARACETAMOL_BARCODE = "6150000000013"  # EAN-13
AMOXICILLIN_BARCODE = "6150000000020"  # EAN-13
UPC_A_BARCODE = "615000000013"  # UPC-A (12 digits); stored as 0615000000013
EAN_8_BARCODE = "61500006"  # EAN-8

# --- Auth and me ---------------------------------------------------------------

REGISTER = {
    "pharmacy_name": "Yaba Community Pharmacy",
    "full_name": "Adaeze Okafor",
    "email": "adaeze@example.com",
    "password": "a-long-passphrase",
}
LOGIN = {"email": "adaeze@example.com", "password": "a-long-passphrase"}
TOKEN = {"access_token": EXAMPLE_TOKEN, "token_type": "bearer"}
CHANGE_PASSWORD = {"current_password": "a-long-passphrase", "new_password": "an-even-longer-passphrase"}

OWNER = {
    "id": OWNER_ID,
    "email": "adaeze@example.com",
    "full_name": "Adaeze Okafor",
    "role": "owner",
    "is_active": True,
    "created_at": CREATED,
}
PHARMACY = {"id": PHARMACY_ID, "name": "Yaba Community Pharmacy", "address": None, "created_at": CREATED}
REGISTERED = {"user": OWNER, "pharmacy": PHARMACY}
ME = {
    "id": OWNER_ID,
    "email": "adaeze@example.com",
    "full_name": "Adaeze Okafor",
    "role": "owner",
    "pharmacy": {"id": PHARMACY_ID, "name": "Yaba Community Pharmacy"},
}

# --- Users ---------------------------------------------------------------------

STAFF = {
    "id": STAFF_ID,
    "email": "tunde@example.com",
    "full_name": "Tunde Bakare",
    "role": "staff",
    "is_active": True,
    "created_at": "2026-11-14T10:05:00Z",
}
CREATE_USER = {
    "email": "tunde@example.com",
    "full_name": "Tunde Bakare",
    "role": "staff",
    "password": "starting-passphrase",
}
UPDATE_USER = [{"role": "manager"}, {"is_active": False}, {"full_name": "Tunde A. Bakare"}]
RESET_PASSWORD = {"new_password": "a-new-starting-passphrase"}
USER_PAGE = {"items": [OWNER, STAFF], "total": 2, "limit": 20, "offset": 0}

# --- Products ------------------------------------------------------------------

PRODUCT = {
    "id": PARACETAMOL_ID,
    "name": "Paracetamol 500 mg Tablets",
    "generic_name": "Paracetamol",
    "strength": "500 mg",
    "form": "tablet",
    "barcode": PARACETAMOL_BARCODE,
    "reorder_level": 20,
    "selling_price_kobo": 50000,
    "is_active": True,
    "created_at": CREATED,
    "updated_at": CREATED,
}
AMOXICILLIN = {
    "id": AMOXICILLIN_ID,
    "name": "Amoxicillin 250 mg/5 ml Suspension, 100 ml",
    "generic_name": "Amoxicillin",
    "strength": "250 mg/5 ml",
    "form": "suspension",
    "barcode": AMOXICILLIN_BARCODE,
    "reorder_level": 10,
    "selling_price_kobo": 185000,
    "is_active": True,
    "created_at": CREATED,
    "updated_at": UPDATED,
}
CREATE_PRODUCT = {
    "name": "Paracetamol 500 mg Tablets",
    "generic_name": "Paracetamol",
    "strength": "500 mg",
    "form": "tablet",
    "barcode": PARACETAMOL_BARCODE,
    "reorder_level": 20,
    "selling_price_kobo": 50000,
}
UPDATE_PRODUCT = [
    {"selling_price_kobo": 55000},
    {"is_active": False},
    {"barcode": UPC_A_BARCODE},
    {"barcode": None},
]
PRODUCT_PAGE = {"items": [AMOXICILLIN, PRODUCT], "total": 2, "limit": 20, "offset": 0}

# --- Health and errors -----------------------------------------------------------

HEALTH = {"status": "ok", "database": "ok"}

VALIDATION_ERROR = {
    "error": {
        "code": "validation_error",
        "message": "The request contains invalid data",
        "details": [
            {
                "location": "body",
                "field": "barcode",
                "message": "The check digit (the last digit) is wrong: it should be 3, not 4. "
                "Check the barcode for a mistyped or swapped digit.",
            }
        ],
    }
}


def error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "details": []}}


def response(description: str, example: dict, model=None) -> dict:
    """A FastAPI `responses` entry showing this example in the docs."""
    entry = {"description": description, "content": {"application/json": {"example": example}}}
    if model is not None:
        entry["model"] = model
    return entry
