import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProductForm(StrEnum):
    TABLET = "tablet"
    CAPSULE = "capsule"
    SYRUP = "syrup"
    SUSPENSION = "suspension"
    INJECTION = "injection"
    CREAM = "cream"
    OINTMENT = "ointment"
    DROPS = "drops"
    INHALER = "inhaler"
    OTHER = "other"


# Must list the same forms as ProductForm. The migration repeats this by hand,
# and tests/test_products_db.py checks they agree.
FORM_CHECK_SQL = (
    "form IN ('tablet', 'capsule', 'syrup', 'suspension', 'injection', "
    "'cream', 'ointment', 'drops', 'inhaler', 'other')"
)

# The largest value a PostgreSQL integer column holds. Requests are limited to
# this, so a huge number is a 422 instead of a database error.
MAX_INTEGER = 2_147_483_647


class Product(Base):
    """A product a pharmacy sells. Never deleted, only archived (is_active=False),
    because stock and sales will point at it."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint(FORM_CHECK_SQL, name="form_valid"),
        # Stored normalized (see app/core/barcodes.py): EAN-8 or EAN-13 digits only
        CheckConstraint("barcode ~ '^([0-9]{8}|[0-9]{13})$'", name="barcode_format"),
        CheckConstraint("reorder_level >= 0", name="reorder_level_not_negative"),
        CheckConstraint("selling_price_kobo >= 0", name="selling_price_not_negative"),
        # A barcode is unique within a pharmacy; two pharmacies can stock the same product
        Index(
            "uq_products_pharmacy_id_barcode",
            "pharmacy_id",
            "barcode",
            unique=True,
            postgresql_where=text("barcode IS NOT NULL"),
        ),
        # Listing a pharmacy's products by name
        Index("ix_products_pharmacy_id_name", "pharmacy_id", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    # RESTRICT: a pharmacy can't be deleted while it has products. No index of
    # its own: both indexes above start with pharmacy_id, which covers it.
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pharmacies.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(200))
    generic_name: Mapped[str | None] = mapped_column(String(200))
    # e.g. "500 mg" or "250 mg/5 ml"
    strength: Mapped[str | None] = mapped_column(String(50))
    form: Mapped[str] = mapped_column(String(20))
    barcode: Mapped[str | None] = mapped_column(String(13))
    # Stock level at which to reorder (used from Milestone 2)
    reorder_level: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    # Money is always whole kobo (100 kobo = 1 naira), never a decimal
    selling_price_kobo: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set by a database trigger on every UPDATE (see the migration), so it is
    # right however the row is changed. FetchedValue tells SQLAlchemy the
    # database changes it, so it reloads the new value.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue()
    )
