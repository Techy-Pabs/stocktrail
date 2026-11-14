"""The product catalogue: /api/v1/products.

Everyone in the pharmacy can list, read and look up products; owners and
managers can add and change them. A product from another pharmacy gets the
same 404 as one that doesn't exist. There is no DELETE: products are
archived (is_active=false), because stock and sales will point at them.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.exceptions import RequestValidationError

from app.core.barcodes import InvalidBarcode, normalize_barcode
from app.core.errors import Conflict, ErrorResponse, NotFound
from app.core.paging import Page, Pagination, paginate, sort_param
from app.dependencies import CurrentUser, DbSession, OwnerOrManager
from app.docs import examples
from app.models import Product, ProductForm
from app.schemas.products import CreateProductRequest, ProductResponse, UpdateProductRequest
from app.services import products as service

router = APIRouter(
    prefix="/products",
    tags=["products"],
    responses={
        401: examples.response(
            "Not logged in", examples.error("not_authenticated", "Could not validate credentials"), ErrorResponse
        )
    },
)

PRODUCT_NOT_FOUND = "Product not found"

NOT_FOUND = {
    404: examples.response(
        "No such product in your pharmacy", examples.error("not_found", PRODUCT_NOT_FOUND), ErrorResponse
    )
}
FORBIDDEN = {
    403: examples.response(
        "Only owners and managers can change products",
        examples.error("forbidden", "You don't have permission to do this"),
        ErrorResponse,
    )
}
DUPLICATE = {
    409: examples.response(
        "Another product in your pharmacy has this barcode",
        {
            "error": {
                "code": "conflict",
                "message": service.DUPLICATE_BARCODE_MESSAGE,
                "details": [{"field": "barcode", "product_id": examples.AMOXICILLIN_ID}],
            }
        },
        ErrorResponse,
    )
}
INVALID = {422: examples.response("Invalid request (see error.details)", examples.VALIDATION_ERROR, ErrorResponse)}

ProductSort = sort_param(
    {"name": Product.name, "created_at": Product.created_at, "selling_price_kobo": Product.selling_price_kobo},
    default="name",
    tie_breaker=Product.id,
)


def pharmacy_product(
    product_id: Annotated[uuid.UUID, Path(description="The product's id", examples=[examples.PARACETAMOL_ID])],
    current_user: CurrentUser,
    db: DbSession,
) -> Product:
    """The product in the URL, only if it belongs to the caller's pharmacy."""
    product = service.get_pharmacy_product(db, current_user.pharmacy_id, product_id)
    if product is None:
        raise NotFound(PRODUCT_NOT_FOUND)
    return product


PharmacyProduct = Annotated[Product, Depends(pharmacy_product)]


def duplicate_barcode(error: service.DuplicateBarcode) -> Conflict:
    details = [{"field": "barcode", "product_id": str(error.existing_id)}] if error.existing_id else []
    return Conflict(service.DUPLICATE_BARCODE_MESSAGE, details=details)


@router.get(
    "",
    response_model=Page[ProductResponse],
    responses={200: examples.response("A page of products", examples.PRODUCT_PAGE)} | INVALID,
)
def list_products(
    current_user: CurrentUser,
    db: DbSession,
    page: Pagination = Depends(),
    order_by: list = Depends(ProductSort),
    q: str | None = Query(
        None, min_length=1, max_length=100, description="Search name and generic name", examples=["paracetamol"]
    ),
    form: ProductForm | None = Query(None, description="Only products in this form"),
    is_active: bool = Query(True, description="true (the default): active products; false: archived ones"),
):
    """Your pharmacy's products, a page at a time. Archived products are
    hidden unless you ask for `is_active=false`."""
    query = service.products_query(current_user.pharmacy_id, q=q, form=form, is_active=is_active)
    return paginate(db, query, page, order_by, ProductResponse.model_validate)


# Declared before /{product_id}, so "barcode" is never read as a product id
@router.get(
    "/barcode/{code}",
    response_model=ProductResponse,
    responses={
        200: examples.response("The product with this barcode", examples.PRODUCT),
        404: examples.response(
            "No product in your pharmacy has this barcode",
            examples.error("not_found", "No product in your pharmacy has this barcode"),
            ErrorResponse,
        ),
    }
    | INVALID,
)
def find_by_barcode(
    code: Annotated[
        str,
        Path(
            description="The scanned or typed barcode (EAN-13, UPC-A or EAN-8). Spaces are ignored, and a "
            "UPC-A finds the same product as its EAN-13 form.",
            openapi_examples={
                "ean13": {"summary": "EAN-13", "value": examples.PARACETAMOL_BARCODE},
                "upca": {"summary": "UPC-A (12 digits)", "value": examples.UPC_A_BARCODE},
                "ean8": {"summary": "EAN-8", "value": examples.EAN_8_BARCODE},
            },
        ),
    ],
    current_user: CurrentUser,
    db: DbSession,
):
    """Find a product by scanning its barcode. Archived products are found too
    (check `is_active`), so a scan never makes a duplicate product."""
    try:
        barcode = normalize_barcode(code)
    except InvalidBarcode as error:
        # The same 422 as any other invalid value (the code itself isn't echoed)
        raise RequestValidationError(
            [{"type": "value_error", "loc": ("path", "code"), "msg": str(error), "input": code}]
        ) from None
    product = service.find_by_barcode(db, current_user.pharmacy_id, barcode)
    if product is None:
        raise NotFound("No product in your pharmacy has this barcode")
    return product


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    responses={200: examples.response("The product", examples.PRODUCT)} | NOT_FOUND | INVALID,
)
def get_product(product: PharmacyProduct):
    """One product, archived or not."""
    return product


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    responses={201: examples.response("The new product", examples.PRODUCT)} | FORBIDDEN | DUPLICATE | INVALID,
)
def create_product(body: CreateProductRequest, user: OwnerOrManager, db: DbSession):
    """Add a product to your pharmacy's catalogue. **Owners and managers only.**"""
    try:
        return service.create_product(db, user.pharmacy_id, body.model_dump())
    except service.DuplicateBarcode as error:
        raise duplicate_barcode(error) from None


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    responses={200: examples.response("The updated product", examples.AMOXICILLIN)}
    | FORBIDDEN
    | NOT_FOUND
    | DUPLICATE
    | INVALID,
)
def update_product(body: UpdateProductRequest, user: OwnerOrManager, product: PharmacyProduct, db: DbSession):
    """Change any of a product's fields. Send `is_active: false` to archive it
    and `true` to restore it. **Owners and managers only.**"""
    try:
        return service.update_product(db, product, body.changes())
    except service.DuplicateBarcode as error:
        raise duplicate_barcode(error) from None
