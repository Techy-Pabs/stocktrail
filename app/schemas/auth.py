from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

# Same rules as ShopAssist. max_length stops someone sending a huge password
# to make the server spend a long time hashing it.
NewPassword = Annotated[str, Field(min_length=8, max_length=128)]
# No min_length when checking an existing password: login shouldn't hint at the rules
ExistingPassword = Annotated[str, Field(max_length=128)]
LowercaseEmail = Annotated[EmailStr, AfterValidator(str.lower)]
# Surrounding spaces removed, then must not be empty
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class StrictRequest(BaseModel):
    # Unknown fields are an error (422), not silently ignored. In particular a
    # client can never send a pharmacy_id: it always comes from the logged in user.
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(StrictRequest):
    pharmacy_name: Name
    full_name: Name
    email: LowercaseEmail
    password: NewPassword


class LoginRequest(StrictRequest):
    email: LowercaseEmail
    password: ExistingPassword


class ChangePasswordRequest(StrictRequest):
    current_password: ExistingPassword
    new_password: NewPassword


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
