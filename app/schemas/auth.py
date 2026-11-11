from pydantic import BaseModel

from app.schemas.common import ExistingPassword, LowercaseEmail, Name, NewPassword, StrictRequest


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
