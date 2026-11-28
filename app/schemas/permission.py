from pydantic import BaseModel, Field, ConfigDict


class PermissionCreate(BaseModel):
    code: str = Field(min_length=2, max_length=100)
    description: str | None = None


class PermissionUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = None


class PermissionResponse(BaseModel):
    id: int
    code: str
    description: str | None

    model_config = ConfigDict(from_attributes=True)