"""The products table's own rules: CHECK constraints, the unique barcode index,
the foreign key and the updated_at trigger. Raw SQL skips the API's checks,
so these prove the database refuses bad data on its own."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import ProductForm
from app.models.product import FORM_CHECK_SQL


@pytest.fixture
def pharmacy_id(engine, session_factory):
    with engine.begin() as conn:
        return conn.scalar(text("INSERT INTO pharmacies (name) VALUES ('Test Pharmacy') RETURNING id"))


def insert_product(engine, pharmacy_id, **overrides):
    values = {
        "pharmacy_id": pharmacy_id,
        "name": "Paracetamol 500 mg Tablets",
        "form": "tablet",
        "barcode": None,
        "reorder_level": 0,
        "selling_price_kobo": 50000,
    } | overrides
    with engine.begin() as conn:
        return conn.scalar(
            text(
                "INSERT INTO products (pharmacy_id, name, form, barcode, reorder_level, selling_price_kobo) "
                "VALUES (:pharmacy_id, :name, :form, :barcode, :reorder_level, :selling_price_kobo) RETURNING id"
            ),
            values,
        )


def test_form_check_lists_every_form():
    for form in ProductForm:
        assert f"'{form.value}'" in FORM_CHECK_SQL
    assert FORM_CHECK_SQL.count("'") == 2 * len(ProductForm)


def test_valid_product_is_accepted_with_defaults(engine, pharmacy_id):
    product_id = insert_product(engine, pharmacy_id)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT reorder_level, is_active, created_at = updated_at FROM products WHERE id = :id"),
            {"id": product_id},
        ).one()
    assert tuple(row) == (0, True, True)


@pytest.mark.parametrize(
    "overrides, constraint",
    [
        ({"selling_price_kobo": -1}, "ck_products_selling_price_not_negative"),
        ({"reorder_level": -1}, "ck_products_reorder_level_not_negative"),
        ({"name": "   "}, "ck_products_name_not_blank"),
        ({"name": ""}, "ck_products_name_not_blank"),
        ({"form": "powder"}, "ck_products_form_valid"),
        ({"form": "TABLET"}, "ck_products_form_valid"),
        ({"barcode": "615000000013"}, "ck_products_barcode_format"),  # UPC-A must be stored as EAN-13
        ({"barcode": "61500000001A"}, "ck_products_barcode_format"),
        ({"barcode": "6150000"}, "ck_products_barcode_format"),
        ({"barcode": ""}, "ck_products_barcode_format"),
    ],
)
def test_database_rejects_bad_values(engine, pharmacy_id, overrides, constraint):
    with pytest.raises(IntegrityError, match=constraint):
        insert_product(engine, pharmacy_id, **overrides)


def test_barcode_is_unique_within_a_pharmacy(engine, pharmacy_id):
    insert_product(engine, pharmacy_id, barcode="6150000000013")

    with pytest.raises(IntegrityError, match="uq_products_pharmacy_id_barcode"):
        insert_product(engine, pharmacy_id, name="Another", barcode="6150000000013")


def test_same_barcode_in_another_pharmacy_is_allowed(engine, pharmacy_id):
    with engine.begin() as conn:
        other_id = conn.scalar(text("INSERT INTO pharmacies (name) VALUES ('Other Pharmacy') RETURNING id"))

    insert_product(engine, pharmacy_id, barcode="6150000000013")
    insert_product(engine, other_id, barcode="6150000000013")


def test_any_number_of_products_without_a_barcode(engine, pharmacy_id):
    for name in ("Gauze Roll", "Cotton Wool", "Plaster"):
        insert_product(engine, pharmacy_id, name=name, barcode=None)


def test_product_needs_a_real_pharmacy(engine, session_factory):
    with pytest.raises(IntegrityError, match="fk_products_pharmacy_id_pharmacies"):
        insert_product(engine, "00000000-0000-0000-0000-000000000000")


def test_pharmacy_with_products_cannot_be_deleted(engine, pharmacy_id):
    insert_product(engine, pharmacy_id)

    with pytest.raises(IntegrityError, match="fk_products_pharmacy_id_pharmacies"), engine.begin() as conn:
        conn.execute(text("DELETE FROM pharmacies WHERE id = :id"), {"id": pharmacy_id})


def test_trigger_sets_updated_at_on_every_update_even_from_raw_sql(engine, pharmacy_id):
    product_id = insert_product(engine, pharmacy_id)
    with engine.connect() as conn:
        created, updated_before = conn.execute(
            text("SELECT created_at, updated_at FROM products WHERE id = :id"), {"id": product_id}
        ).one()

    with engine.begin() as conn:
        # Even an UPDATE that tries to set updated_at itself gets the real time
        conn.execute(
            text("UPDATE products SET selling_price_kobo = 1, updated_at = '2000-01-01' WHERE id = :id"),
            {"id": product_id},
        )
    with engine.connect() as conn:
        created_after, updated_after = conn.execute(
            text("SELECT created_at, updated_at FROM products WHERE id = :id"), {"id": product_id}
        ).one()

    assert created_after == created
    assert updated_after > updated_before


def test_indexes_exist(engine):
    with engine.connect() as conn:
        indexes = dict(
            conn.execute(text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'products'")).all()
        )
    assert "UNIQUE INDEX uq_products_pharmacy_id_barcode" in indexes["uq_products_pharmacy_id_barcode"]
    assert "(pharmacy_id, barcode) WHERE (barcode IS NOT NULL)" in indexes["uq_products_pharmacy_id_barcode"]
    assert "(pharmacy_id, name)" in indexes["ix_products_pharmacy_id_name"]
