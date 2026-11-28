from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.common import (
    DepartmentCreate, DepartmentOut, ProjectCreate, ProjectOut, TaskCreate, TaskOut
)
from app.services import core

router = APIRouter()

@router.get("/departments", response_model=list[DepartmentOut], tags=["Departments"])
def get_departments(db: Session = Depends(get_db)):
    return core.list_departments(db)

@router.post("/departments", response_model=DepartmentOut, status_code=201, tags=["Departments"])
def post_department(payload: DepartmentCreate, db: Session = Depends(get_db)):
    try:
        return core.create_department(db, payload)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Department name already exists")

@router.get("/projects", response_model=list[ProjectOut], tags=["Projects"])
def get_projects(db: Session = Depends(get_db)):
    return core.list_projects(db)

@router.post("/projects", response_model=ProjectOut, status_code=201, tags=["Projects"])
def post_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    try:
        return core.create_project(db, payload)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Invalid owner_id or project data")

@router.get("/tasks", response_model=list[TaskOut], tags=["Tasks"])
def get_tasks(project_id: int | None = None, db: Session = Depends(get_db)):
    return core.list_tasks(db, project_id)

@router.post("/tasks", response_model=TaskOut, status_code=201, tags=["Tasks"])
def post_task(payload: TaskCreate, db: Session = Depends(get_db)):
    try:
        return core.create_task(db, payload)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Invalid project_id, assignee_id or task data")
