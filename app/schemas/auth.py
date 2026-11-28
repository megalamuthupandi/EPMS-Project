
from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    company_code: str = Field(min_length=3, max_length=40)
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    company_code: str = Field(min_length=3, max_length=40)


class UserResponse(BaseModel):
    id: int
    company_id: int
    employee_code: str
    full_name: str
    email: EmailStr
    department_id: int | None
    role_id: int
    role_serial_id: int | None = None
    is_active: bool

    model_config = {
        "from_attributes": True
    }


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_token: str | None = None
    expires_in_minutes: int | None = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20)
    new_password: str = Field(min_length=8, max_length=128)
