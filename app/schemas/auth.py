from pydantic import BaseModel, ConfigDict

from app.docs import examples
from app.schemas.common import ExistingPassword, LowercaseEmail, Name, NewPassword, StrictRequest


class RegisterRequest(StrictRequest):
    model_config = ConfigDict(json_schema_extra={"examples": [examples.REGISTER]})

    pharmacy_name: Name
    full_name: Name
    email: LowercaseEmail
    password: NewPassword


class LoginRequest(StrictRequest):
    model_config = ConfigDict(json_schema_extra={"examples": [examples.LOGIN]})

    email: LowercaseEmail
    password: ExistingPassword


class ChangePasswordRequest(StrictRequest):
    model_config = ConfigDict(json_schema_extra={"examples": [examples.CHANGE_PASSWORD]})

    current_password: ExistingPassword
    new_password: NewPassword


class TokenResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [examples.TOKEN]})

    access_token: str
    token_type: str = "bearer"
