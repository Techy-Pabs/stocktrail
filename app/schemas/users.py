"""Request bodies for owner-only user management (/api/v1/users)."""

from typing import Self

from pydantic import ConfigDict, model_validator

from app.docs import examples
from app.models import Role
from app.schemas.common import LowercaseEmail, Name, NewPassword, StrictRequest


class CreateUserRequest(StrictRequest):
    model_config = ConfigDict(json_schema_extra={"examples": [examples.CREATE_USER]})

    # No pharmacy here: the new user always joins the owner's pharmacy
    email: LowercaseEmail
    full_name: Name
    role: Role
    # The starting password; the user can change it with PATCH /me/password
    password: NewPassword


class UpdateUserRequest(StrictRequest):
    """Only the fields sent are changed. At least one is required."""

    model_config = ConfigDict(json_schema_extra={"examples": examples.UPDATE_USER})

    full_name: Name | None = None
    role: Role | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Send at least one of full_name, role or is_active")
        # Leaving a field out means "don't change it"; sending null is a mistake
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} can't be null; leave it out to keep the current value")
        return self


class ResetPasswordRequest(StrictRequest):
    model_config = ConfigDict(json_schema_extra={"examples": [examples.RESET_PASSWORD]})

    # The user's new starting password
    new_password: NewPassword
