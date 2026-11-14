"""The product catalogue inside one pharmacy. Every function takes the
pharmacy from the caller (the logged in user), never from the request."""

import uuid
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.paging import like_pattern
from app.models import Product, ProductForm

# Name of the unique index on (pharmacy_id, barcode); PostgreSQL reports it
# as the constraint when two products would share a barcode
BARCODE_UNIQUE_INDEX = "uq_products_pharmacy_id_barcode"

DUPLICATE_BARCODE_MESSAGE = "Another product in your pharmacy already has this barcode"


class DuplicateBarcode(Exception):
    def __init__(self, existing_id: uuid.UUID | None = None):
        # The other product with this barcode, when known, so the client can show it
        self.existing_id = existing_id
        super().__init__(DUPLICATE_BARCODE_MESSAGE)


def products_query(
    pharmacy_id: uuid.UUID, *, q: str | None = None, form: ProductForm | None = None, is_active: bool = True
) -> Select:
    """The pharmacy's products matching the filters (no order: the caller sorts).

    Only active products unless is_active=False (archived ones) is asked for.
    """
    query = select(Product).where(Product.pharmacy_id == pharmacy_id, Product.is_active == is_active)
    if form is not None:
        query = query.where(Product.form == form)
    if q:
        pattern = like_pattern(q)
        query = query.where(
            or_(Product.name.ilike(pattern, escape="\\"), Product.generic_name.ilike(pattern, escape="\\"))
        )
    return query


def get_pharmacy_product(db: Session, pharmacy_id: uuid.UUID, product_id: uuid.UUID) -> Product | None:
    """The product, only if it belongs to this pharmacy (archived included)."""
    return db.scalar(select(Product).where(Product.id == product_id, Product.pharmacy_id == pharmacy_id))


def find_by_barcode(db: Session, pharmacy_id: uuid.UUID, barcode: str) -> Product | None:
    """The product with this (already normalized) barcode in this pharmacy, archived included."""
    return db.scalar(select(Product).where(Product.pharmacy_id == pharmacy_id, Product.barcode == barcode))


def _check_barcode_free(db: Session, pharmacy_id: uuid.UUID, barcode: str | None, except_id=None) -> None:
    if barcode is None:
        return
    existing = find_by_barcode(db, pharmacy_id, barcode)
    if existing is not None and existing.id != except_id:
        raise DuplicateBarcode(existing.id)


def _commit(db: Session) -> None:
    """Commit, turning a barcode clash caught by the unique index into DuplicateBarcode.

    The check before saving covers the usual case; the index catches two
    requests saving the same barcode at the same moment.
    """
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        diag = getattr(error.orig, "diag", None)
        if getattr(diag, "constraint_name", None) == BARCODE_UNIQUE_INDEX:
            raise DuplicateBarcode from None
        raise


def create_product(db: Session, pharmacy_id: uuid.UUID, fields: dict[str, Any]) -> Product:
    _check_barcode_free(db, pharmacy_id, fields.get("barcode"))
    product = Product(pharmacy_id=pharmacy_id, **fields)
    db.add(product)
    _commit(db)
    db.refresh(product)
    return product


def update_product(db: Session, product: Product, changes: dict[str, Any]) -> Product:
    """Apply only the given changes. A value of None clears an optional field."""
    if "barcode" in changes:
        _check_barcode_free(db, product.pharmacy_id, changes["barcode"], except_id=product.id)
    for name, value in changes.items():
        setattr(product, name, value)
    _commit(db)
    # Reloads updated_at, which the database trigger set
    db.refresh(product)
    return product
