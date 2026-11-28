from pydantic import BaseModel, EmailStr, Field, ConfigDict


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    department_id: int | None = None
    role_id: int


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    department_id: int | None = None
    role_id: int | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: int
    company_id: int
    employee_code: str
    full_name: str
    email: EmailStr
    department_id: int | None
    role_id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)