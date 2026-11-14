"""create products

Revision ID: 2f92bd8f480b
Revises: dcf43775badb
Create Date: 2026-11-14

Slice C: each pharmacy's product catalogue. Products are archived
(is_active = false), never deleted.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2f92bd8f480b"
down_revision: str | Sequence[str] | None = "dcf43775badb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("pharmacy_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("generic_name", sa.String(length=200), nullable=True),
        sa.Column("strength", sa.String(length=50), nullable=True),
        sa.Column("form", sa.String(length=20), nullable=False),
        sa.Column("barcode", sa.String(length=13), nullable=True),
        sa.Column("reorder_level", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("selling_price_kobo", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.ForeignKeyConstraint(
            ["pharmacy_id"],
            ["pharmacies.id"],
            name=op.f("fk_products_pharmacy_id_pharmacies"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_products_name_not_blank")),
        # Must match app.models.product.ProductForm
        sa.CheckConstraint(
            "form IN ('tablet', 'capsule', 'syrup', 'suspension', 'injection', "
            "'cream', 'ointment', 'drops', 'inhaler', 'other')",
            name=op.f("ck_products_form_valid"),
        ),
        # Barcodes are stored normalized: 8 digits (EAN-8) or 13 (EAN-13, with
        # UPC-A stored as EAN-13). The check digit is verified by the API.
        sa.CheckConstraint("barcode ~ '^([0-9]{8}|[0-9]{13})$'", name=op.f("ck_products_barcode_format")),
        sa.CheckConstraint("reorder_level >= 0", name=op.f("ck_products_reorder_level_not_negative")),
        # Whole kobo, never negative
        sa.CheckConstraint("selling_price_kobo >= 0", name=op.f("ck_products_selling_price_not_negative")),
    )

    # A barcode is unique within one pharmacy. Partial ("WHERE barcode IS NOT
    # NULL") so any number of products can have no barcode.
    op.create_index(
        "uq_products_pharmacy_id_barcode",
        "products",
        ["pharmacy_id", "barcode"],
        unique=True,
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )
    # Listing and searching a pharmacy's products in name order
    op.create_index("ix_products_pharmacy_id_name", "products", ["pharmacy_id", "name"])

    # updated_at is set by the database on every UPDATE, however the row is
    # changed. The function is generic, so later tables can use it too.
    op.execute(
        """
        CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER products_set_updated_at
        BEFORE UPDATE ON products
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER products_set_updated_at ON products")
    op.execute("DROP FUNCTION set_updated_at()")
    op.drop_index("ix_products_pharmacy_id_name", table_name="products")
    op.drop_index(
        "uq_products_pharmacy_id_barcode", table_name="products", postgresql_where=sa.text("barcode IS NOT NULL")
    )
    op.drop_table("products")
