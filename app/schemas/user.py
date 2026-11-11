import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import Role


class ORMResponse(BaseModel):
    # from_attributes lets these be built straight from model objects.
    # Only the fields listed are sent back, so the password hash never is.
    model_config = ConfigDict(from_attributes=True)


class PharmacySummary(ORMResponse):
    id: uuid.UUID
    name: str


class PharmacyResponse(PharmacySummary):
    address: str | None
    created_at: datetime


class UserResponse(ORMResponse):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime


class RegisterResponse(BaseModel):
    user: UserResponse
    pharmacy: PharmacyResponse


class MeResponse(ORMResponse):
    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    pharmacy: PharmacySummary
