from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.entities import Task, Project, ProjectMember, User
from app.routers.auth import get_current_user

router = APIRouter(prefix="/completed-work", tags=["Completed Work"])

def role(user): return (user.role.name if user.role else "").upper().replace(" ", "_")

@router.get("")
def completed_work(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = role(user)
    tq = select(Task).join(Project, Project.id == Task.project_id).where(Project.company_id == user.company_id, Task.status == "DONE")
    pq = select(Project).where(Project.company_id == user.company_id, Project.status == "COMPLETED")
    if r in {"EMPLOYEE", "EMP"}:
        tq = tq.where(Task.assignee_id == user.id); pq = pq.where(False)
    elif r in {"TEAM_LEAD", "TL"}:
        pids = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id, ProjectMember.project_role.in_(["LEAD", "TEAM_LEAD", "TL"]))
        tq = tq.where(Task.project_id.in_(pids)); pq = pq.where(Project.id.in_(pids))
    elif r in {"PROJECT_MANAGER", "PM"}:
        tq = tq.where(Project.owner_id == user.id); pq = pq.where(Project.owner_id == user.id)
    elif r not in {"ADMIN", "ADMINISTRATOR"}:
        tq = tq.where(False); pq = pq.where(False)
    tasks = db.scalars(tq.order_by(Task.completed_at.desc().nullslast(), Task.id.desc())).all()
    projects = db.scalars(pq.order_by(Project.completed_at.desc().nullslast(), Project.id.desc())).all()
    return {
      "tasks": [{"id":t.id,"title":t.title,"project_id":t.project_id,"project_name":t.project.name if t.project else "","assignee":t.assignee.full_name if t.assignee else None,"completed_by":db.get(User,t.completed_by).full_name if t.completed_by and db.get(User,t.completed_by) else None,"completed_at":t.completed_at.isoformat() if t.completed_at else None} for t in tasks],
      "projects": [{"id":p.id,"name":p.name,"completed_by":db.get(User,p.completed_by).full_name if p.completed_by and db.get(User,p.completed_by) else None,"completed_at":p.completed_at.isoformat() if p.completed_at else None} for p in projects],
      "summary":{"completed_tasks":len(tasks),"completed_projects":len(projects)}
    }
