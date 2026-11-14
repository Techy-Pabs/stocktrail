"""The Swagger docs: descriptions, examples on every endpoint, and every
example barcode valid (and made up)."""

import re

import pytest

from app.core.barcodes import normalize_barcode
from app.main import app

SPEC = app.openapi()
OPERATIONS = [
    (method.upper(), path, operation)
    for path, methods in SPEC["paths"].items()
    for method, operation in methods.items()
]


def all_values(node, key=None):
    """Every (key, value) pair anywhere in the spec, including inside lists."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from all_values(v, k)
    elif isinstance(node, list):
        for item in node:
            yield from all_values(item, key)
    else:
        yield key, node


def test_api_has_a_description():
    assert "Nigerian community pharmacies" in SPEC["info"]["description"]
    assert SPEC["info"]["summary"]


def test_every_tag_has_a_description():
    described = {tag["name"]: tag.get("description") for tag in SPEC["tags"]}
    used = {tag for _, _, operation in OPERATIONS for tag in operation["tags"]}

    assert used == {"auth", "me", "users", "products", "health"}
    for tag in used:
        assert described.get(tag), f"tag {tag} has no description"


def has_example(content: dict) -> bool:
    schema = content.get("schema", {})
    if "example" in content or "examples" in content:
        return True
    if "examples" in schema:
        return True
    ref = schema.get("$ref")
    if ref:
        return "examples" in SPEC["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    return False


@pytest.mark.parametrize("method, path, operation", OPERATIONS, ids=[f"{m} {p}" for m, p, _ in OPERATIONS])
def test_every_endpoint_has_request_and_response_examples(method, path, operation):
    assert operation.get("summary") and operation.get("description"), "no summary or description"

    body = operation.get("requestBody")
    if body:
        assert has_example(body["content"]["application/json"]), "request body has no example"

    for status, response in operation["responses"].items():
        content = response.get("content", {}).get("application/json")
        if content is not None:
            assert has_example(content), f"response {status} has no example"


def test_every_example_barcode_is_valid_and_made_up():
    candidates = []
    for key, value in all_values(SPEC):
        if not isinstance(value, str):
            continue
        # Anything in a barcode field, and any 8, 12 or 13 digit number anywhere
        # (which includes the barcode lookup's path examples)
        if key == "barcode" or re.fullmatch(r"\d{8}|\d{12,13}", value):
            candidates.append(value)
    # Barcodes quoted inside descriptions too
    for _, value in all_values(SPEC):
        if isinstance(value, str):
            candidates += re.findall(r"(?<!\d)(?:\d{13}|\d{12}|\d{8})(?!\d)", value)

    barcodes = sorted(set(candidates))
    assert len(barcodes) >= 4  # EAN-13s, the UPC-A and the EAN-8 are all there
    for barcode in barcodes:
        stored = normalize_barcode(barcode)  # raises if the check digit is wrong
        assert stored.lstrip("0").startswith("615"), f"{barcode} doesn't start with 615"


def test_prices_in_examples_are_whole_kobo():
    prices = [value for key, value in all_values(SPEC) if key == "selling_price_kobo"]

    assert prices
    assert all(isinstance(price, int) and price >= 0 for price in prices)
