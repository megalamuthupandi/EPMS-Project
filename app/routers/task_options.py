from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.entities import Project, ProjectMember, User
from app.routers.auth import get_current_user

router = APIRouter(prefix="/tasks", tags=["Tasks"])

@router.get("/assignees")
def eligible_assignees(project_id:int=Query(...,ge=1),db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    project=db.get(Project,project_id)
    if not project: raise HTTPException(404,"Project not found")
    role=(user.role.name if user.role else "").upper().replace(" ","_")
    if role=="EMPLOYEE": raise HTTPException(403,"Employees cannot assign tasks")
    rows=db.execute(select(User.id,User.full_name).join(ProjectMember,ProjectMember.user_id==User.id).where(ProjectMember.project_id==project_id,User.is_active.is_(True)).order_by(User.full_name)).all()
    result=[{"id":r.id,"full_name":r.full_name} for r in rows]
    if project.owner_id not in {x['id'] for x in result}:
        owner=db.get(User,project.owner_id)
        if owner: result.insert(0,{"id":owner.id,"full_name":owner.full_name})
    return result
