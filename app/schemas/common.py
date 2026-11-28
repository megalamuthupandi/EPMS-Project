from datetime import date
from pydantic import BaseModel, ConfigDict, Field

class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class DepartmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = None

class DepartmentOut(ORMBase):
    id: int
    name: str
    description: str | None
    is_active: bool

class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = None
    owner_id: int
    start_date: date | None = None
    due_date: date | None = None

class ProjectOut(ORMBase):
    id: int
    name: str
    description: str | None
    owner_id: int
    status: str

class TaskCreate(BaseModel):
    project_id: int
    title: str = Field(min_length=2, max_length=180)
    description: str | None = None
    assignee_id: int | None = None
    priority: str = "MEDIUM"
    due_date: date | None = None

class TaskOut(ORMBase):
    id: int
    project_id: int
    assignee_id: int | None
    title: str
    status: str
    priority: str
