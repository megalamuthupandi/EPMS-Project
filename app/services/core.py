from sqlalchemy.orm import Session
from app.models.entities import Department, Project, Task
from app.schemas.common import DepartmentCreate, ProjectCreate, TaskCreate

def create_department(db: Session, data: DepartmentCreate):
    obj = Department(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

def list_departments(db: Session):
    return db.query(Department).order_by(Department.id).all()

def create_project(db: Session, data: ProjectCreate):
    obj = Project(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

def list_projects(db: Session):
    return db.query(Project).order_by(Project.id.desc()).all()

def create_task(db: Session, data: TaskCreate):
    obj = Task(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

def list_tasks(db: Session, project_id: int | None = None):
    query = db.query(Task)
    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
    return query.order_by(Task.id.desc()).all()
