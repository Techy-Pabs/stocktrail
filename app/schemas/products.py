"""Request and response bodies for the product catalogue (/api/v1/products)."""

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.barcodes import normalize_barcode
from app.docs import examples
from app.models.product import MAX_INTEGER, ProductForm
from app.schemas.common import Name, StrictRequest

# Validated and normalized (UPC-A becomes EAN-13) before it reaches the database
Barcode = Annotated[str, AfterValidator(normalize_barcode)]
# Optional text: surrounding spaces removed; an empty string is a 422 (send null instead)
OptionalName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Strength = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
# strict: a real JSON whole number only. "500" (a string), 500.5 and true are all
# rejected, so a price can't arrive in the wrong unit or as a decimal by accident.
Kobo = Annotated[int, Field(strict=True, ge=0, le=MAX_INTEGER, description="Whole kobo (100 kobo = 1 naira)")]
ReorderLevel = Annotated[int, Field(strict=True, ge=0, le=MAX_INTEGER, description="Reorder at or below this stock")]


class CreateProductRequest(StrictRequest):
    # No pharmacy here: the product always joins the caller's pharmacy
    model_config = ConfigDict(json_schema_extra={"examples": [examples.CREATE_PRODUCT]})

    name: Name
    generic_name: OptionalName | None = None
    strength: Strength | None = None
    form: ProductForm
    barcode: Barcode | None = Field(None, description="EAN-13, UPC-A or EAN-8; UPC-A is stored as EAN-13")
    reorder_level: ReorderLevel = 0
    selling_price_kobo: Kobo


# Fields that may be set to null (cleared) in a PATCH; the rest are required values
CLEARABLE_FIELDS = {"generic_name", "strength", "barcode"}


class UpdateProductRequest(StrictRequest):
    """Only the fields sent are changed. At least one is required.
    generic_name, strength and barcode can be cleared with null."""

    model_config = ConfigDict(json_schema_extra={"examples": examples.UPDATE_PRODUCT})

    name: Name | None = None
    generic_name: OptionalName | None = None
    strength: Strength | None = None
    form: ProductForm | None = None
    barcode: Barcode | None = None
    reorder_level: ReorderLevel | None = None
    selling_price_kobo: Kobo | None = None
    is_active: bool | None = Field(None, description="false archives the product, true restores it")

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Send at least one field to change")
        for name in self.model_fields_set - CLEARABLE_FIELDS:
            if getattr(self, name) is None:
                raise ValueError(f"{name} can't be null; leave it out to keep the current value")
        return self

    def changes(self) -> dict:
        """Only the fields the client sent, with their new values (None clears)."""
        return {name: getattr(self, name) for name in self.model_fields_set}


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, json_schema_extra={"examples": [examples.PRODUCT]})

    id: uuid.UUID
    name: str
    generic_name: str | None
    strength: str | None
    form: ProductForm
    barcode: str | None
    reorder_level: int
    selling_price_kobo: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
