from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, case
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import User, Project, ProjectMember, Task, Milestone
from app.routers.auth import get_current_user

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _scope_project_ids(db: Session, user: User):
    role = (user.role.name if user.role else "").upper()
    if role in {"ADMIN", "ADMINISTRATOR"}:
        return select(Project.id).where(Project.company_id == user.company_id)
    if role in {"PROJECT_MANAGER", "PROJECT MANAGER", "PM"}:
        owned = select(Project.id).where(Project.owner_id == user.id)
        assigned = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
        return owned.union(assigned)
    if role in {"TEAM_LEAD", "TEAM LEAD", "TL"}:
        return select(ProjectMember.project_id).where(
            ProjectMember.user_id == user.id,
            func.upper(ProjectMember.project_role).in_(["LEAD", "TEAM_LEAD"]),
        )
    if role in {"EMPLOYEE", "EMP"}:
        member_projects = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
        task_projects = select(Task.project_id).where(Task.assignee_id == user.id)
        return member_projects.union(task_projects)
    raise HTTPException(status_code=403, detail="Analytics access is not configured for this role")


def _project_filter(query, project_ids):
    return query if project_ids is None else query.where(Project.id.in_(project_ids))


@router.get("/dashboard")
def dashboard_analytics(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project_ids = _scope_project_ids(db, user)
    project_query = _project_filter(select(Project), project_ids)
    scoped_projects = project_query.subquery()
    task_base = select(Task).where(Task.project_id.in_(select(scoped_projects.c.id)))
    if (user.role.name if user.role else "").upper() in {"EMPLOYEE", "EMP"}:
        # Employee sees assigned tasks and projects they belong to; task counts remain their own tasks.
        task_base = select(Task).where(Task.assignee_id == user.id)

    total_projects = db.scalar(select(func.count()).select_from(scoped_projects)) or 0
    project_status_rows = db.execute(
        select(Project.status, func.count()).where(Project.id.in_(select(scoped_projects.c.id))).group_by(Project.status)
    ).all()
    total_tasks = db.scalar(select(func.count()).select_from(task_base.subquery())) or 0
    task_status_rows = db.execute(
        select(Task.status, func.count()).where(Task.id.in_(select(task_base.subquery().c.id))).group_by(Task.status)
    ).all()
    today = date.today()
    overdue = db.scalar(select(func.count()).select_from(task_base.where(
        Task.due_date.is_not(None), Task.due_date < today, Task.status != "DONE"
    ).subquery())) or 0
    total_milestones = db.scalar(select(func.count()).select_from(Milestone).where(
        Milestone.project_id.in_(select(scoped_projects.c.id))
    )) or 0
    completed_projects = dict(project_status_rows).get("COMPLETED", 0)
    completed_tasks = dict(task_status_rows).get("DONE", 0)

    employee_load = db.execute(
        select(User.full_name, func.count(Task.id).label("task_count"))
        .join(Task, Task.assignee_id == User.id)
        .where(Task.project_id.in_(select(scoped_projects.c.id)))
        .group_by(User.id, User.full_name)
        .order_by(func.count(Task.id).desc())
        .limit(10)
    ).all()
    if (user.role.name if user.role else "").upper() in {"EMPLOYEE", "EMP"}:
        employee_load = [(user.full_name, total_tasks)]

    since = today - timedelta(days=183)
    # Group by the timestamp bucket itself, then format it in Python.
    # This avoids PostgreSQL's GROUP BY error caused by grouping date_trunc()
    # while selecting to_char(date_trunc(...)).
    month_bucket = func.date_trunc("month", Task.created_at)
    monthly_rows = db.execute(
        select(
            month_bucket.label("month_start"),
            func.count(Task.id).label("created"),
            func.sum(case((Task.status == "DONE", 1), else_=0)).label("completed"),
        )
        .where(
            Task.id.in_(select(task_base.subquery().c.id)),
            Task.created_at >= since,
        )
        .group_by(month_bucket)
        .order_by(month_bucket)
    ).all()

    return {
        "role": user.role.name if user.role else None,
        "summary": {
            "total_projects": total_projects,
            "active_projects": dict(project_status_rows).get("ACTIVE", 0),
            "completed_projects": completed_projects,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "pending_tasks": sum(v for k, v in dict(task_status_rows).items() if k in {"TODO", "IN_PROGRESS", "IN_REVIEW", "BLOCKED"}),
            "overdue_tasks": overdue,
            "total_milestones": total_milestones,
        },
        "project_status": [{"status": k, "count": v} for k, v in project_status_rows],
        "task_status": [{"status": k, "count": v} for k, v in task_status_rows],
        "employee_workload": [{"employee": n, "tasks": c} for n, c in employee_load],
        "monthly_performance": [
            {
                "month": m.strftime("%Y-%m") if hasattr(m, "strftime") else str(m)[:7],
                "created": c or 0,
                "completed": d or 0,
            }
            for m, c, d in monthly_rows
        ],
    }
