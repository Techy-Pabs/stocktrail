"""The product catalogue: /api/v1/products."""

import time
from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.models import Product, Role
from app.services import products as service
from tests.helpers import assert_error, assert_unauthorized, headers_for

PARACETAMOL = {
    "name": "Paracetamol 500 mg Tablets",
    "generic_name": "Paracetamol",
    "strength": "500 mg",
    "form": "tablet",
    "barcode": "6150000000013",
    "reorder_level": 20,
    "selling_price_kobo": 50000,
}
AMOXICILLIN = {
    "name": "Amoxicillin 250 mg/5 ml Suspension",
    "generic_name": "Amoxicillin",
    "strength": "250 mg/5 ml",
    "form": "suspension",
    "barcode": "6150000000020",
    "selling_price_kobo": 185000,
}


@pytest.fixture
def pharmacy(make_pharmacy):
    return make_pharmacy("Ada Pharmacy")


@pytest.fixture
def other_pharmacy(make_pharmacy):
    return make_pharmacy("Other Pharmacy")


@pytest.fixture
def owner(pharmacy, make_user):
    return make_user(pharmacy, role=Role.OWNER)


@pytest.fixture
def manager(pharmacy, make_user):
    return make_user(pharmacy, role=Role.MANAGER)


@pytest.fixture
def staff(pharmacy, make_user):
    return make_user(pharmacy, role=Role.STAFF)


def create(client, user, body):
    return client.post("/api/v1/products", json=body, headers=headers_for(user))


def count_products(db) -> int:
    return db.scalar(select(func.count()).select_from(Product))


# --- Create and read -------------------------------------------------------------


def test_create_product(client, owner, db):
    response = create(client, owner, PARACETAMOL)

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body) == {
        "id", "name", "generic_name", "strength", "form", "barcode", "reorder_level",
        "selling_price_kobo", "is_active", "created_at", "updated_at",
    }  # fmt: skip
    assert {k: body[k] for k in PARACETAMOL} == PARACETAMOL
    assert body["is_active"] is True
    saved = db.get(Product, body["id"])
    assert saved.pharmacy_id == owner.pharmacy_id


def test_create_with_only_required_fields(client, owner):
    response = create(client, owner, {"name": "Gauze Roll", "form": "other", "selling_price_kobo": 30000})

    assert response.status_code == 201
    body = response.json()
    assert (body["generic_name"], body["strength"], body["barcode"], body["reorder_level"]) == (None, None, None, 0)


def test_text_fields_are_trimmed(client, owner):
    body = create(client, owner, PARACETAMOL | {"name": "  Paracetamol  ", "strength": " 500 mg "}).json()

    assert (body["name"], body["strength"]) == ("Paracetamol", "500 mg")


def test_upca_barcode_is_stored_as_ean13(client, owner):
    response = create(client, owner, PARACETAMOL | {"barcode": "615000000013"})

    assert response.json()["barcode"] == "0615000000013"


def test_barcode_spaces_are_stripped_when_saving(client, owner):
    response = create(client, owner, PARACETAMOL | {"barcode": "615 0000 000013"})

    assert response.json()["barcode"] == "6150000000013"


def test_get_product(client, staff, pharmacy, make_product):
    product = make_product(pharmacy)

    response = client.get(f"/api/v1/products/{product.id}", headers=headers_for(staff))

    assert response.status_code == 200
    assert response.json()["id"] == str(product.id)


def test_get_archived_product(client, staff, pharmacy, make_product):
    product = make_product(pharmacy, is_active=False)

    response = client.get(f"/api/v1/products/{product.id}", headers=headers_for(staff))

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_unknown_product_is_404(client, staff):
    response = client.get("/api/v1/products/00000000-0000-0000-0000-000000000000", headers=headers_for(staff))

    assert_error(response, 404, "not_found", "Product not found")


def test_products_are_never_deleted(client, owner, pharmacy, make_product):
    product = make_product(pharmacy)

    assert_error(client.delete(f"/api/v1/products/{product.id}", headers=headers_for(owner)), 405, "method_not_allowed")


# --- Barcode lookup --------------------------------------------------------------


def lookup(client, user, code):
    return client.get(f"/api/v1/products/barcode/{code}", headers=headers_for(user))


def test_lookup_by_barcode(client, staff, pharmacy, make_product):
    product = make_product(pharmacy, barcode="6150000000013")

    response = lookup(client, staff, "6150000000013")

    assert response.status_code == 200
    assert response.json()["id"] == str(product.id)


def test_lookup_ignores_spaces(client, staff, pharmacy, make_product):
    product = make_product(pharmacy, barcode="6150000000013")

    assert lookup(client, staff, "615%200000%20000013").json()["id"] == str(product.id)


def test_upca_and_ean13_forms_find_the_same_product(client, owner, staff):
    # Saved as a 12 digit UPC-A, found by either form
    product_id = create(client, owner, PARACETAMOL | {"barcode": "615000000013"}).json()["id"]

    assert lookup(client, staff, "615000000013").json()["id"] == product_id
    assert lookup(client, staff, "0615000000013").json()["id"] == product_id


def test_saved_as_ean13_found_by_upca(client, owner, staff):
    product_id = create(client, owner, PARACETAMOL | {"barcode": "0036000291452"}).json()["id"]

    assert lookup(client, staff, "036000291452").json()["id"] == product_id


def test_lookup_finds_archived_products(client, staff, pharmacy, make_product):
    make_product(pharmacy, barcode="6150000000013", is_active=False)

    response = lookup(client, staff, "6150000000013")

    assert response.status_code == 200
    assert response.json()["is_active"] is False


def test_lookup_unknown_barcode_is_404(client, staff):
    assert_error(lookup(client, staff, "6150000000013"), 404, "not_found")


@pytest.mark.parametrize(
    "code, message",
    [
        ("6150000000014", "should be 3, not 4"),
        ("12345", "this one has 5"),
        ("61500000000AB", "only contain the digits 0 to 9"),
    ],
)
def test_lookup_invalid_barcode_is_422(client, staff, code, message):
    error = assert_error(lookup(client, staff, code), 422, "validation_error")

    assert len(error["details"]) == 1
    detail = error["details"][0]
    assert (detail["location"], detail["field"]) == ("path", "code")
    assert message in detail["message"]
    assert code not in detail["message"]


# --- Roles -----------------------------------------------------------------------


def test_staff_can_list_read_and_look_up(client, staff, pharmacy, make_product):
    product = make_product(pharmacy, barcode="6150000000013")
    headers = headers_for(staff)

    assert client.get("/api/v1/products", headers=headers).status_code == 200
    assert client.get(f"/api/v1/products/{product.id}", headers=headers).status_code == 200
    assert lookup(client, staff, "6150000000013").status_code == 200


def test_staff_get_403_on_create_and_update(client, staff, pharmacy, make_product, db):
    product = make_product(pharmacy)
    headers = headers_for(staff)

    assert_error(client.post("/api/v1/products", json=AMOXICILLIN, headers=headers), 403, "forbidden")
    response = client.patch(f"/api/v1/products/{product.id}", json={"selling_price_kobo": 1}, headers=headers)
    assert_error(response, 403, "forbidden")
    db.expire_all()
    assert count_products(db) == 1
    assert db.get(Product, product.id).selling_price_kobo == 50000


@pytest.mark.parametrize("role", [Role.OWNER, Role.MANAGER])
def test_owner_and_manager_can_do_everything(client, pharmacy, make_user, role):
    user = make_user(pharmacy, role=role)
    headers = headers_for(user)

    created = client.post("/api/v1/products", json=PARACETAMOL, headers=headers)
    assert created.status_code == 201
    product_id = created.json()["id"]
    assert client.get("/api/v1/products", headers=headers).json()["total"] == 1
    assert client.get(f"/api/v1/products/{product_id}", headers=headers).status_code == 200
    assert lookup(client, user, "6150000000013").status_code == 200
    updated = client.patch(f"/api/v1/products/{product_id}", json={"selling_price_kobo": 55000}, headers=headers)
    assert updated.json()["selling_price_kobo"] == 55000


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/api/v1/products"),
        ("POST", "/api/v1/products"),
        ("GET", "/api/v1/products/00000000-0000-0000-0000-000000000000"),
        ("PATCH", "/api/v1/products/00000000-0000-0000-0000-000000000000"),
        ("GET", "/api/v1/products/barcode/6150000000013"),
    ],
)
def test_not_logged_in_gets_401(client, method, path):
    assert_unauthorized(client.request(method, path, json=PARACETAMOL))


def test_deactivated_manager_loses_access(client, manager, db):
    headers = headers_for(manager)
    manager.is_active = False
    db.commit()

    assert_unauthorized(client.get("/api/v1/products", headers=headers))


# --- Duplicate barcodes ----------------------------------------------------------


def test_same_barcode_in_same_pharmacy_is_409(client, owner, db):
    first = create(client, owner, PARACETAMOL).json()

    response = create(client, owner, AMOXICILLIN | {"barcode": PARACETAMOL["barcode"]})

    error = assert_error(response, 409, "conflict", service.DUPLICATE_BARCODE_MESSAGE)
    assert error["details"] == [{"field": "barcode", "product_id": first["id"]}]
    assert count_products(db) == 1


def test_upca_and_its_ean13_form_count_as_the_same_barcode(client, owner):
    assert create(client, owner, PARACETAMOL | {"barcode": "615000000013"}).status_code == 201

    response = create(client, owner, AMOXICILLIN | {"barcode": "0615000000013"})

    assert_error(response, 409, "conflict")


def test_same_barcode_in_two_pharmacies_is_allowed(client, owner, other_pharmacy, make_user):
    other_owner = make_user(other_pharmacy, role=Role.OWNER)

    assert create(client, owner, PARACETAMOL).status_code == 201
    assert create(client, other_owner, PARACETAMOL).status_code == 201


def test_duplicate_caught_by_the_unique_index_is_409(client, owner, db, monkeypatch):
    # Two requests at the same moment: both pass the check before saving,
    # and the database's unique index stops the second
    create(client, owner, PARACETAMOL)
    monkeypatch.setattr(service, "_check_barcode_free", lambda *args, **kwargs: None)

    response = create(client, owner, AMOXICILLIN | {"barcode": PARACETAMOL["barcode"]})

    assert_error(response, 409, "conflict", service.DUPLICATE_BARCODE_MESSAGE)
    assert count_products(db) == 1


def test_changing_to_a_barcode_in_use_is_409(client, owner):
    create(client, owner, PARACETAMOL)
    second = create(client, owner, AMOXICILLIN).json()

    response = client.patch(
        f"/api/v1/products/{second['id']}", json={"barcode": PARACETAMOL["barcode"]}, headers=headers_for(owner)
    )

    assert_error(response, 409, "conflict")


def test_keeping_your_own_barcode_is_fine(client, owner):
    product = create(client, owner, PARACETAMOL).json()

    response = client.patch(
        f"/api/v1/products/{product['id']}",
        json={"barcode": "615 0000 000013", "name": "Paracetamol Tablets"},
        headers=headers_for(owner),
    )

    assert response.status_code == 200


def test_many_products_without_a_barcode(client, owner):
    for name in ("Gauze Roll", "Cotton Wool", "Plaster"):
        assert create(client, owner, {"name": name, "form": "other", "selling_price_kobo": 10000}).status_code == 201


def test_archived_product_still_holds_its_barcode(client, owner, pharmacy, make_product):
    make_product(pharmacy, barcode="6150000000013", is_active=False)

    assert_error(create(client, owner, PARACETAMOL), 409, "conflict")


# --- Update ----------------------------------------------------------------------


def test_update_any_field(client, owner):
    product = create(client, owner, PARACETAMOL).json()
    changes = AMOXICILLIN | {"reorder_level": 5}

    body = client.patch(f"/api/v1/products/{product['id']}", json=changes, headers=headers_for(owner)).json()

    assert {k: body[k] for k in changes} == changes


def test_update_only_changes_fields_sent(client, owner):
    product = create(client, owner, PARACETAMOL).json()

    body = client.patch(
        f"/api/v1/products/{product['id']}", json={"selling_price_kobo": 55000}, headers=headers_for(owner)
    ).json()

    assert body["selling_price_kobo"] == 55000
    assert {k: body[k] for k in PARACETAMOL if k != "selling_price_kobo"} == {
        k: v for k, v in PARACETAMOL.items() if k != "selling_price_kobo"
    }


def test_optional_fields_can_be_cleared_with_null(client, owner):
    product = create(client, owner, PARACETAMOL).json()

    body = client.patch(
        f"/api/v1/products/{product['id']}",
        json={"barcode": None, "generic_name": None, "strength": None},
        headers=headers_for(owner),
    ).json()

    assert (body["barcode"], body["generic_name"], body["strength"]) == (None, None, None)


def test_archive_and_restore(client, owner, staff):
    product = create(client, owner, PARACETAMOL).json()
    path = f"/api/v1/products/{product['id']}"

    assert client.patch(path, json={"is_active": False}, headers=headers_for(owner)).json()["is_active"] is False
    assert client.get("/api/v1/products", headers=headers_for(staff)).json()["total"] == 0
    assert client.patch(path, json={"is_active": True}, headers=headers_for(owner)).json()["is_active"] is True
    assert client.get("/api/v1/products", headers=headers_for(staff)).json()["total"] == 1


def when(timestamp: str) -> datetime:
    # Parsed, not compared as text: the text only has microseconds when they aren't 0
    return datetime.fromisoformat(timestamp)


def test_updated_at_changes_on_update_and_created_at_does_not(client, owner):
    product = create(client, owner, PARACETAMOL).json()
    assert product["updated_at"] == product["created_at"]
    time.sleep(0.01)

    body = client.patch(
        f"/api/v1/products/{product['id']}", json={"selling_price_kobo": 55000}, headers=headers_for(owner)
    ).json()

    assert body["created_at"] == product["created_at"]
    assert when(body["updated_at"]) > when(product["updated_at"])
    # And again on a second change
    time.sleep(0.01)
    again = client.patch(f"/api/v1/products/{product['id']}", json={"is_active": False}, headers=headers_for(owner))
    assert when(again.json()["updated_at"]) > when(body["updated_at"])


# --- Validation ------------------------------------------------------------------


@pytest.mark.parametrize(
    "change, field",
    [
        ({"selling_price_kobo": -1}, "selling_price_kobo"),
        ({"selling_price_kobo": 500.5}, "selling_price_kobo"),
        ({"selling_price_kobo": "50000"}, "selling_price_kobo"),
        ({"selling_price_kobo": True}, "selling_price_kobo"),
        ({"selling_price_kobo": 2_147_483_648}, "selling_price_kobo"),
        ({"reorder_level": -1}, "reorder_level"),
        ({"name": "   "}, "name"),
        ({"name": "x" * 201}, "name"),
        ({"strength": "x" * 51}, "strength"),
        ({"generic_name": ""}, "generic_name"),
        ({"form": "powder"}, "form"),
        ({"barcode": "6150000000014"}, "barcode"),
        ({"barcode": "ABC"}, "barcode"),
        ({"pharmacy_id": "00000000-0000-0000-0000-000000000000"}, "pharmacy_id"),
        ({"is_active": False}, "is_active"),
    ],
    ids=[
        "negative-price", "decimal-price", "price-as-string", "price-as-bool", "price-too-big",
        "negative-reorder", "blank-name", "long-name", "long-strength", "empty-generic", "unknown-form",
        "bad-check-digit", "letters-barcode", "pharmacy_id", "is_active-on-create",
    ],
)  # fmt: skip
def test_create_validation(client, owner, db, change, field):
    response = create(client, owner, PARACETAMOL | change)

    error = assert_error(response, 422, "validation_error")
    assert [d["field"] for d in error["details"]] == [field]
    assert count_products(db) == 0


def test_missing_required_fields(client, owner):
    error = assert_error(create(client, owner, {}), 422, "validation_error")

    assert {d["field"] for d in error["details"]} == {"name", "form", "selling_price_kobo"}


def test_wrong_check_digit_message_names_the_right_digit(client, owner):
    error = assert_error(create(client, owner, PARACETAMOL | {"barcode": "6150000000014"}), 422, "validation_error")

    assert error["details"][0]["message"].startswith("The check digit (the last digit) is wrong: it should be 3, not 4")


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"form": None},
        {"selling_price_kobo": None},
        {"reorder_level": None},
        {"is_active": None},
        {"selling_price_kobo": -5},
        {"form": "powder"},
        {"pharmacy_id": "00000000-0000-0000-0000-000000000000"},
    ],
    ids=[
        "empty",
        "null-name",
        "null-form",
        "null-price",
        "null-reorder",
        "null-active",
        "negative",
        "form",
        "pharmacy",
    ],
)
def test_update_validation(client, owner, pharmacy, make_product, db, body):
    product = make_product(pharmacy)

    response = client.patch(f"/api/v1/products/{product.id}", json=body, headers=headers_for(owner))

    assert_error(response, 422, "validation_error")
    db.expire_all()
    assert db.get(Product, product.id).selling_price_kobo == 50000


# --- Tenant isolation ------------------------------------------------------------


@pytest.fixture
def other_product(other_pharmacy, make_product):
    return make_product(
        other_pharmacy, name="Zinc Oxide Searchable Cream", generic_name="Zinc Oxide", form="cream",
        barcode="6150000000037",
    )  # fmt: skip


def test_other_pharmacys_products_never_appear_in_list_or_search(client, staff, pharmacy, make_product, other_product):
    mine = make_product(pharmacy)
    headers = headers_for(staff)

    listed = client.get("/api/v1/products", headers=headers, params={"limit": 100}).json()
    assert [item["id"] for item in listed["items"]] == [str(mine.id)]
    assert listed["total"] == 1
    for params in ({"q": "Zinc"}, {"q": "Searchable"}, {"form": "cream"}, {"is_active": "false"}):
        found = client.get("/api/v1/products", headers=headers, params=params).json()
        assert (found["items"], found["total"]) == ([], 0), params


@pytest.mark.parametrize("role", [Role.OWNER, Role.MANAGER, Role.STAFF])
def test_other_pharmacys_product_is_404_on_every_route(client, pharmacy, make_user, other_product, db, role):
    user = make_user(pharmacy, role=role)
    headers = headers_for(user)

    assert_error(client.get(f"/api/v1/products/{other_product.id}", headers=headers), 404, "not_found")
    assert_error(lookup(client, user, "6150000000037"), 404, "not_found")
    if role != Role.STAFF:  # staff get 403 on PATCH before the product is even looked up
        response = client.patch(f"/api/v1/products/{other_product.id}", json={"name": "Hijacked"}, headers=headers)
        assert_error(response, 404, "not_found", "Product not found")
    db.expire_all()
    assert db.get(Product, other_product.id).name == "Zinc Oxide Searchable Cream"


def test_created_product_always_joins_the_callers_pharmacy(client, owner, other_pharmacy, db):
    product_id = create(client, owner, PARACETAMOL).json()["id"]

    assert db.get(Product, product_id).pharmacy_id == owner.pharmacy_id != other_pharmacy.id


# --- Listing: paging, search, filters, sorting -------------------------------------


@pytest.fixture
def catalogue(pharmacy, make_product):
    """A small catalogue of five active products and one archived one."""
    return [
        make_product(pharmacy, "Paracetamol 500 mg Tablets", generic_name="Paracetamol", selling_price_kobo=50000),
        make_product(pharmacy, "Panadol Extra", generic_name="Paracetamol + Caffeine", selling_price_kobo=120000),
        make_product(
            pharmacy, "Amoxil Suspension", generic_name="Amoxicillin", form="suspension", selling_price_kobo=185000
        ),
        make_product(
            pharmacy, "Ventolin Inhaler", generic_name="Salbutamol", form="inhaler", selling_price_kobo=450000
        ),
        make_product(pharmacy, "Vitamin C 100% Natural_Pure", form="tablet", selling_price_kobo=80000),
        make_product(pharmacy, "Old Cough Syrup", form="syrup", selling_price_kobo=90000, is_active=False),
    ]


def names(client, user, **params):
    response = client.get("/api/v1/products", headers=headers_for(user), params={"limit": 100} | params)
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


def test_archived_hidden_by_default_and_shown_with_is_active_false(client, staff, catalogue):
    assert "Old Cough Syrup" not in names(client, staff)
    assert len(names(client, staff)) == 5
    assert names(client, staff, is_active="false") == ["Old Cough Syrup"]
    assert len(names(client, staff, is_active="true")) == 5


def test_search_name_and_generic_name_case_insensitively(client, staff, catalogue):
    assert set(names(client, staff, q="PARACETAMOL")) == {"Paracetamol 500 mg Tablets", "Panadol Extra"}
    assert names(client, staff, q="amoxicillin") == ["Amoxil Suspension"]
    assert names(client, staff, q="ventolin") == ["Ventolin Inhaler"]


def test_search_takes_percent_and_underscore_literally(client, staff, catalogue):
    assert names(client, staff, q="%") == ["Vitamin C 100% Natural_Pure"]
    assert names(client, staff, q="_") == ["Vitamin C 100% Natural_Pure"]
    assert names(client, staff, q="0%") == ["Vitamin C 100% Natural_Pure"]
    assert names(client, staff, q="l_P") == ["Vitamin C 100% Natural_Pure"]
    assert names(client, staff, q="a_a") == []  # "_" is not a wildcard


def test_search_combines_with_filters(client, staff, catalogue):
    assert names(client, staff, q="cough") == []  # archived
    assert names(client, staff, q="cough", is_active="false") == ["Old Cough Syrup"]
    assert names(client, staff, form="tablet", q="vitamin") == ["Vitamin C 100% Natural_Pure"]


def test_filter_by_form(client, staff, catalogue):
    assert names(client, staff, form="inhaler") == ["Ventolin Inhaler"]
    assert names(client, staff, form="injection") == []
    assert_error(client.get("/api/v1/products?form=powder", headers=headers_for(staff)), 422, "validation_error")


def test_paging_total_counts_every_match(client, staff, catalogue):
    headers = headers_for(staff)

    first = client.get("/api/v1/products", headers=headers, params={"limit": 2}).json()
    second = client.get("/api/v1/products", headers=headers, params={"limit": 2, "offset": 2}).json()
    third = client.get("/api/v1/products", headers=headers, params={"limit": 2, "offset": 4}).json()

    assert [p["total"] for p in (first, second, third)] == [5, 5, 5]
    assert [len(p["items"]) for p in (first, second, third)] == [2, 2, 1]
    ids = [item["id"] for page in (first, second, third) for item in page["items"]]
    assert len(set(ids)) == 5


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"sort": "barcode"}, {"q": ""}])
def test_bad_paging_sort_or_search_is_422(client, staff, params):
    response = client.get("/api/v1/products", headers=headers_for(staff), params=params)

    assert_error(response, 422, "validation_error")


def database_order(db, pharmacy, sort: str) -> list[str]:
    column = getattr(Product, sort.removeprefix("-"))
    order = column.desc() if sort.startswith("-") else column.asc()
    query = select(Product.name).where(Product.pharmacy_id == pharmacy.id, Product.is_active.is_(True))
    return list(db.scalars(query.order_by(order, Product.id)))


@pytest.mark.parametrize(
    "sort", ["name", "-name", "created_at", "-created_at", "selling_price_kobo", "-selling_price_kobo"]
)
def test_every_sort_field_works(client, staff, catalogue, db, pharmacy, sort):
    assert names(client, staff, sort=sort) == database_order(db, pharmacy, sort)


def test_default_sort_is_name_and_price_sort_is_numeric(client, staff, catalogue, db, pharmacy):
    assert names(client, staff) == database_order(db, pharmacy, "name")
    assert names(client, staff, sort="selling_price_kobo")[0] == "Paracetamol 500 mg Tablets"  # 50000
    assert names(client, staff, sort="-selling_price_kobo")[0] == "Ventolin Inhaler"  # 450000


def test_equal_sort_values_keep_a_stable_order(client, staff, pharmacy, make_product):
    products = [make_product(pharmacy, "Same Name", selling_price_kobo=100) for _ in range(7)]
    expected = sorted(str(p.id) for p in products)
    headers = headers_for(staff)

    for sort in ("name", "-name", "selling_price_kobo"):
        paged = []
        for offset in range(0, 7, 3):
            page = client.get("/api/v1/products", headers=headers, params={"limit": 3, "offset": offset, "sort": sort})
            paged += [item["id"] for item in page.json()["items"]]
        assert paged == expected, sort
