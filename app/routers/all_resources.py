
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, create_model
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import (
    Department,
    Role,
    Project,
    ProjectMember,
    Task,
    TaskStatusHistory,
    Milestone,
    Comment,
    Notification,
    AuditLog,
    User,
    ChatRoom,
    ChatRoomMember,
)
from app.routers.auth import require_permission, get_current_user

router = APIRouter()


@router.post("/notifications/deadline-reminders/check")
def create_deadline_reminders(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    today = date.today()
    role = (current_user.role.name if current_user.role else "").upper().replace(" ", "_")
    stmt = select(Task).join(Project, Project.id == Task.project_id).where(Project.company_id == current_user.company_id, Task.status != "DONE", Task.due_date.is_not(None), Task.due_date <= today + timedelta(days=1))
    if role in {"EMPLOYEE", "EMP"}:
        stmt = stmt.where(Task.assignee_id == current_user.id)
    elif role in {"TEAM_LEAD", "TL"}:
        stmt = stmt.join(ProjectMember, ProjectMember.project_id == Task.project_id).where(ProjectMember.user_id == current_user.id, ProjectMember.project_role.in_(["LEAD", "TEAM_LEAD", "TL"]))
    elif role in {"PROJECT_MANAGER", "PM"}:
        stmt = stmt.where(Project.owner_id == current_user.id)
    elif role not in {"ADMIN", "ADMINISTRATOR"}:
        return {"created": 0}
    tasks = db.scalars(stmt).unique().all()
    created = 0
    for task in tasks:
        marker = f"[deadline-task:{task.id}:{today.isoformat()}]"
        exists = db.scalar(select(Notification.id).where(Notification.user_id == current_user.id, Notification.message.contains(marker)))
        if not exists:
            label = "overdue" if task.due_date < today else ("due today" if task.due_date == today else "due tomorrow")
            db.add(Notification(user_id=current_user.id, title="Task deadline reminder", message=f"{task.title} is {label}. {marker}", is_read=False)); created += 1
    if created: db.commit()
    return {"created": created}


RESOURCE_MODELS = {
    "departments": Department,
    "roles": Role,
    "projects": Project,
    "project_members": ProjectMember,
    "tasks": Task,
    "task_status_history": TaskStatusHistory,
    "milestones": Milestone,
    "comments": Comment,
    "notifications": Notification,
    "audit_logs": AuditLog,
}


RESOURCE_PERMISSIONS = {
    "departments": {
        "GET": "ROLE_MANAGE",
        "POST": "ROLE_MANAGE",
        "PATCH": "ROLE_MANAGE",
        "DELETE": "ROLE_MANAGE",
    },
    "roles": {
        "GET": "ROLE_MANAGE",
        "POST": "ROLE_MANAGE",
        "PATCH": "ROLE_MANAGE",
        "DELETE": "ROLE_MANAGE",
    },
    "projects": {
        "GET": "PROJECT_VIEW",
        "POST": "PROJECT_CREATE",
        "PATCH": "PROJECT_UPDATE",
        "DELETE": "PROJECT_DELETE",
    },
    "project_members": {
        "GET": "PROJECT_VIEW",
        "POST": "MEMBER_ASSIGN",
        "PATCH": "MEMBER_ASSIGN",
        "DELETE": "MEMBER_ASSIGN",
    },
    "tasks": {
        "GET": "PROJECT_VIEW",
        "POST": "TASK_CREATE",
        "PATCH": "TASK_UPDATE_ASSIGNED",
        "DELETE": "TASK_ASSIGN",
    },
    "task_status_history": {
        "GET": "PROJECT_VIEW",
        "POST": "TASK_UPDATE_ASSIGNED",
        "PATCH": "TASK_UPDATE_ASSIGNED",
        "DELETE": "TASK_ASSIGN",
    },
    "milestones": {
        "GET": "PROJECT_VIEW",
        "POST": "PROJECT_CREATE",
        "PATCH": "PROJECT_UPDATE",
        "DELETE": "PROJECT_DELETE",
    },
    "comments": {
        "GET": "PROJECT_VIEW",
        "POST": "TASK_UPDATE_ASSIGNED",
        "PATCH": "TASK_UPDATE_ASSIGNED",
        "DELETE": "TASK_ASSIGN",
    },
    "notifications": {
        "GET": "PROJECT_VIEW",
        "POST": "USER_MANAGE",
        "PATCH": "PROJECT_VIEW",
        "DELETE": "USER_MANAGE",
    },
    "audit_logs": {
        "GET": "ROLE_MANAGE",
        "POST": "ROLE_MANAGE",
        "PATCH": "ROLE_MANAGE",
        "DELETE": "ROLE_MANAGE",
    },
}


def _column_python_type(column):
    try:
        python_type = column.type.python_type
    except (AttributeError, NotImplementedError):
        python_type = str

    if python_type in (
        int,
        str,
        bool,
        float,
        date,
        datetime,
        Decimal,
        UUID,
        bytes,
    ):
        return python_type

    return str


def _build_schema(model, schema_name: str, *, mode: str):
    fields = {}

    for column in model.__table__.columns:

        if mode == "create" and column.primary_key:
            continue

        annotation = _column_python_type(column)

        has_default = (
            column.default is not None
            or column.server_default is not None
        )

        nullable = bool(column.nullable)

        if mode in ("update", "response"):
            fields[column.name] = (Optional[annotation], None)

        elif (model is Project and column.name == "company_id") or nullable or has_default:
            fields[column.name] = (Optional[annotation], None)

        else:
            fields[column.name] = (annotation, ...)

    return create_model(
        schema_name,
        __config__=ConfigDict(
            from_attributes=True,
            extra="forbid",
        ),
        **fields,
    )


def _serialize(obj):
    return {
        column.name: getattr(obj, column.name)
        for column in obj.__table__.columns
    }


def _validate_payload(
    model,
    payload: dict[str, Any],
    *,
    partial: bool = False,
):
    columns = {
        column.name: column
        for column in model.__table__.columns
    }

    unknown = set(payload) - set(columns)

    if unknown:
        raise HTTPException(
            status_code=422,
            detail={"unknown_fields": sorted(unknown)},
        )

    data = dict(payload)

    for key, value in data.items():
        if value is None and not columns[key].nullable:
            raise HTTPException(
                status_code=422,
                detail=f"{key} cannot be null",
            )

    if not partial:
        missing = [
            column.name
            for column in model.__table__.columns
            if (
                not column.primary_key
                and not column.nullable
                and column.default is None
                and column.server_default is None
                and not (model is Project and column.name == "company_id")
                and column.name not in data
            )
        ]

        if missing:
            raise HTTPException(
                status_code=422,
                detail={"missing_fields": missing},
            )

    data.pop("id", None)

    return data


def _tenant_statement(statement, resource_name, current_user):
    company_id = current_user.company_id
    if resource_name == "projects":
        return statement.where(Project.company_id == company_id)
    if resource_name == "project_members":
        return statement.where(ProjectMember.project_id.in_(select(Project.id).where(Project.company_id == company_id)))
    if resource_name == "tasks":
        return statement.where(Task.project_id.in_(select(Project.id).where(Project.company_id == company_id)))
    if resource_name == "milestones":
        return statement.where(Milestone.project_id.in_(select(Project.id).where(Project.company_id == company_id)))
    if resource_name == "task_status_history":
        return statement.where(TaskStatusHistory.task_id.in_(select(Task.id).join(Project, Project.id == Task.project_id).where(Project.company_id == company_id)))
    if resource_name == "comments":
        return statement.where(Comment.task_id.in_(select(Task.id).join(Project, Project.id == Task.project_id).where(Project.company_id == company_id)))
    if resource_name == "notifications":
        return statement.where(Notification.user_id.in_(select(User.id).where(User.company_id == company_id)))
    if resource_name == "audit_logs":
        return statement.where(AuditLog.user_id.in_(select(User.id).where(User.company_id == company_id)))
    return statement


def _is_employee(user):
    return bool(user.role and user.role.name.upper() == "EMPLOYEE")


def _is_project_manager(user):
    return bool(user.role and user.role.name.upper() == "PROJECT_MANAGER")


def _employee_project_ids(current_user):
    """Projects the employee belongs to or has an assigned task in."""
    member_projects = select(ProjectMember.project_id).where(
        ProjectMember.user_id == current_user.id
    )
    assigned_task_projects = select(Task.project_id).where(
        Task.assignee_id == current_user.id
    )
    return member_projects.union(assigned_task_projects)


def _employee_can_access(model, obj, current_user):
    if not _is_employee(current_user):
        return True
    if model is Project:
        return obj.id in set(
            # Use the relationships already loaded for this record where possible.
            [membership.project_id for membership in obj.members if membership.user_id == current_user.id]
        ) or any(task.assignee_id == current_user.id for task in obj.tasks)
    if model is Task:
        return obj.assignee_id == current_user.id
    return True


def register_resource(resource_name: str, model):

    tag = resource_name.replace("_", " ").title()

    base_path = f"/{resource_name}"

    CreateSchema = _build_schema(
        model,
        f"{model.__name__}Create",
        mode="create",
    )

    UpdateSchema = _build_schema(
        model,
        f"{model.__name__}Update",
        mode="update",
    )

    ResponseSchema = _build_schema(
        model,
        f"{model.__name__}Response",
        mode="response",
    )

    # LIST ITEMS

    def list_items(
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
        record_id: Optional[int] = Query(None, ge=1),
        project_id: Optional[int] = Query(None, ge=1),
        status: Optional[str] = Query(None),
        priority: Optional[str] = Query(None),
        assignee_id: Optional[int] = Query(None, ge=1),
        user_id: Optional[int] = Query(None, ge=1),
        project_role: Optional[str] = Query(None),
        search: Optional[str] = Query(None),
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user),
    ):
        statement = _tenant_statement(select(model), resource_name, current_user)
        # Server-side filters used by the Projects, Tasks and Project Members pages.
        if resource_name in {"projects", "tasks", "project_members"}:
            if record_id is not None:
                statement = statement.where(model.id == record_id)
            if project_id is not None and resource_name in {"tasks", "project_members"}:
                statement = statement.where(model.project_id == project_id)
            if status and resource_name in {"projects", "tasks"}:
                statement = statement.where(model.status == status.upper())
            elif resource_name == "projects":
                statement = statement.where(Project.status != "COMPLETED")
            elif resource_name == "tasks":
                statement = statement.where(Task.status != "DONE")
            if priority and resource_name == "tasks":
                statement = statement.where(Task.priority == priority.upper())
            if assignee_id is not None and resource_name == "tasks":
                statement = statement.where(Task.assignee_id == assignee_id)
            if user_id is not None and resource_name == "project_members":
                statement = statement.where(ProjectMember.user_id == user_id)
            if project_role and resource_name == "project_members":
                statement = statement.where(ProjectMember.project_role == project_role.upper())
            if search and search.strip():
                term = f"%{search.strip()}%"
                if resource_name == "projects":
                    statement = statement.where(or_(Project.name.ilike(term), Project.description.ilike(term)))
                elif resource_name == "tasks":
                    statement = statement.where(or_(Task.title.ilike(term), Task.description.ilike(term)))
        # Employee visibility is enforced by the API, not only by the frontend.
        if _is_employee(current_user) and resource_name == "projects":
            statement = statement.where(Project.id.in_(_employee_project_ids(current_user)))
        elif _is_employee(current_user) and resource_name == "tasks":
            statement = statement.where(Task.assignee_id == current_user.id)
        # Notifications are private: each signed-in user sees only their own.
        if resource_name == "notifications":
            statement = statement.where(Notification.user_id == current_user.id)
            statement = statement.order_by(Notification.created_at.desc(), Notification.id.desc())
        else:
            # Stable ordering prevents IDs appearing in arbitrary database order.
            statement = statement.order_by(model.id.asc())
        rows = db.scalars(statement.offset(skip).limit(limit)).all()
        return [_serialize(row) for row in rows]

    # CREATE ITEM

    def create_item(
        payload,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user),
    ):
        data = _validate_payload(
            model,
            payload.model_dump(exclude_unset=True),
        )
        if resource_name == "projects":
            data["company_id"] = current_user.company_id
            owner = db.scalar(select(User).where(User.id == data.get("owner_id"), User.company_id == current_user.company_id))
            if not owner:
                raise HTTPException(status_code=422, detail="Project owner must belong to your company")
            if _is_project_manager(current_user) and data.get("owner_id") != current_user.id:
                raise HTTPException(status_code=403, detail="Project Managers can create only projects they own")
        if resource_name == "project_members":
            project = db.scalar(select(Project).where(Project.id == data.get("project_id"), Project.company_id == current_user.company_id))
            member = db.scalar(select(User).where(User.id == data.get("user_id"), User.company_id == current_user.company_id))
            if not project or not member:
                raise HTTPException(status_code=422, detail="Project and member must belong to your company")

        if resource_name == "tasks":
            project = db.scalar(select(Project).where(Project.id == data.get("project_id"), Project.company_id == current_user.company_id))
            if not project:
                raise HTTPException(status_code=422, detail="Project must belong to your company")
            if data.get("assignee_id") is not None and not db.scalar(select(User.id).where(User.id == data["assignee_id"], User.company_id == current_user.company_id)):
                raise HTTPException(status_code=422, detail="Assignee must belong to your company")
        if resource_name == "milestones":
            if not db.scalar(select(Project.id).where(Project.id == data.get("project_id"), Project.company_id == current_user.company_id)):
                raise HTTPException(status_code=422, detail="Project must belong to your company")
        if resource_name in {"task_status_history", "comments"}:
            task_id = data.get("task_id")
            if not db.scalar(select(Task.id).join(Project, Project.id == Task.project_id).where(Task.id == task_id, Project.company_id == current_user.company_id)):
                raise HTTPException(status_code=422, detail="Task must belong to your company")
            actor_id = data.get("changed_by") if resource_name == "task_status_history" else data.get("user_id")
            if actor_id is not None and not db.scalar(select(User.id).where(User.id == actor_id, User.company_id == current_user.company_id)):
                raise HTTPException(status_code=422, detail="User must belong to your company")
        if resource_name == "notifications":
            if data.get("user_id") != current_user.id:
                raise HTTPException(status_code=403, detail="You may create notifications only for yourself")
        if resource_name == "audit_logs" and data.get("user_id") is not None:
            if not db.scalar(select(User.id).where(User.id == data["user_id"], User.company_id == current_user.company_id)):
                raise HTTPException(status_code=422, detail="Audit user must belong to your company")

        if resource_name == "tasks" and data.get("assignee_id") is not None:
            project_id = data.get("project_id")
            eligible = db.scalar(select(ProjectMember.id).where(ProjectMember.project_id == project_id, ProjectMember.user_id == data["assignee_id"]))
            project = db.get(Project, project_id)
            if not eligible and (not project or project.owner_id != data["assignee_id"]):
                raise HTTPException(status_code=422, detail="Assignee must belong to the selected project")

        obj = model(**data)
        if resource_name == "tasks" and obj.status == "DONE":
            obj.completed_by = current_user.id
            obj.completed_at = datetime.now(timezone.utc)
        if resource_name == "projects" and obj.status == "COMPLETED":
            obj.completed_by = current_user.id
            obj.completed_at = datetime.now(timezone.utc)

        db.add(obj)

        try:
            db.commit()
            db.refresh(obj)
            if resource_name == "projects":
                room = ChatRoom(project_id=obj.id, created_by=obj.owner_id)
                db.add(room)
                db.flush()
                db.add(ChatRoomMember(room_id=room.id, user_id=obj.owner_id, added_by=obj.owner_id))
            if resource_name in {"projects", "tasks"}:
                db.add(AuditLog(user_id=current_user.id, action=f"{resource_name[:-1].upper()}_CREATED", entity_type=resource_name[:-1].upper(), entity_id=obj.id, details=f"Created {getattr(obj, 'name', getattr(obj, 'title', resource_name))}"))
            if resource_name == "tasks" and obj.assignee_id:
                db.add(Notification(user_id=obj.assignee_id, title="Task assigned", message=f"You were assigned: {obj.title}", is_read=False))
            db.commit()
            return _serialize(obj)

        except IntegrityError as exc:
            db.rollback()

            # Show the actual database error in terminal
            print("\n========== DATABASE ERROR ==========")
            print(exc.orig)
            print("====================================\n")

            raise HTTPException(
                status_code=409,
                detail=str(exc.orig),
            ) from exc

    # GET SINGLE ITEM

    def get_item(
        item_id: int,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user),
    ):
        obj = db.scalar(_tenant_statement(select(model).where(model.id == item_id), resource_name, current_user))

        if obj is None:
            raise HTTPException(
                status_code=404,
                detail=f"{model.__name__} not found",
            )

        if _is_employee(current_user):
            allowed = True
            if resource_name == "projects":
                allowed = db.scalar(
                    select(Project.id).where(
                        Project.id == item_id,
                        or_(
                            Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == current_user.id)),
                            Project.id.in_(select(Task.project_id).where(Task.assignee_id == current_user.id)),
                        ),
                    )
                ) is not None
            elif resource_name == "tasks":
                allowed = obj.assignee_id == current_user.id
            if not allowed:
                raise HTTPException(status_code=404, detail=f"{model.__name__} not found")

        return _serialize(obj)

    # UPDATE ITEM

    def update_item(
        item_id: int,
        payload,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user),
    ):
        obj = db.scalar(_tenant_statement(select(model).where(model.id == item_id), resource_name, current_user))

        if obj is None:
            raise HTTPException(
                status_code=404,
                detail=f"{model.__name__} not found",
            )

        # Project Managers may view every company project, but may edit only projects they own.
        if resource_name == "projects" and _is_project_manager(current_user) and obj.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can edit only projects you own")

        if _is_employee(current_user):
            if resource_name == "projects":
                allowed = db.scalar(select(Project.id).where(
                    Project.id == item_id,
                    or_(
                        Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == current_user.id)),
                        Project.id.in_(select(Task.project_id).where(Task.assignee_id == current_user.id)),
                    ),
                )) is not None
            elif resource_name == "tasks":
                allowed = obj.assignee_id == current_user.id
            else:
                allowed = True
            if not allowed:
                raise HTTPException(status_code=404, detail=f"{model.__name__} not found")

        data = _validate_payload(
            model,
            payload.model_dump(exclude_unset=True),
            partial=True,
        )
        if "company_id" in data:
            raise HTTPException(status_code=403, detail="Company assignment cannot be changed")
        if resource_name == "projects" and "owner_id" in data:
            if _is_project_manager(current_user) and data["owner_id"] != current_user.id:
                raise HTTPException(status_code=403, detail="Project Managers cannot transfer project ownership")
            if not db.scalar(select(User.id).where(User.id == data["owner_id"], User.company_id == current_user.company_id)):
                raise HTTPException(status_code=422, detail="Project owner must belong to your company")
        if resource_name == "project_members":
            project_id_check = data.get("project_id", obj.project_id)
            user_id_check = data.get("user_id", obj.user_id)
            if not db.scalar(select(Project.id).where(Project.id == project_id_check, Project.company_id == current_user.company_id)) or not db.scalar(select(User.id).where(User.id == user_id_check, User.company_id == current_user.company_id)):
                raise HTTPException(status_code=422, detail="Project and member must belong to your company")
        if resource_name in {"task_status_history", "comments"}:
            task_id_check = data.get("task_id", obj.task_id)
            if not db.scalar(select(Task.id).join(Project, Project.id == Task.project_id).where(Task.id == task_id_check, Project.company_id == current_user.company_id)):
                raise HTTPException(status_code=422, detail="Task must belong to your company")
            actor_key = "changed_by" if resource_name == "task_status_history" else "user_id"
            actor_id = data.get(actor_key, getattr(obj, actor_key))
            if not db.scalar(select(User.id).where(User.id == actor_id, User.company_id == current_user.company_id)):
                raise HTTPException(status_code=422, detail="User must belong to your company")
        if resource_name == "tasks":
            project_id_check = data.get("project_id", obj.project_id)
            if not db.scalar(select(Project.id).where(Project.id == project_id_check, Project.company_id == current_user.company_id)):
                raise HTTPException(status_code=422, detail="Project must belong to your company")
            if data.get("assignee_id") is not None and not db.scalar(select(User.id).where(User.id == data["assignee_id"], User.company_id == current_user.company_id)):
                raise HTTPException(status_code=422, detail="Assignee must belong to your company")
        if resource_name == "milestones" and "project_id" in data:
            if not db.scalar(select(Project.id).where(Project.id == data["project_id"], Project.company_id == current_user.company_id)):
                raise HTTPException(status_code=422, detail="Project must belong to your company")
        if resource_name == "tasks" and data.get("assignee_id") is not None:
            project_id = data.get("project_id", obj.project_id)
            eligible = db.scalar(select(ProjectMember.id).where(ProjectMember.project_id == project_id, ProjectMember.user_id == data["assignee_id"]))
            project = db.get(Project, project_id)
            if not eligible and (not project or project.owner_id != data["assignee_id"]):
                raise HTTPException(status_code=422, detail="Assignee must belong to the selected project")

        # Team Leads may change only a milestone's completion flag.
        if resource_name == "milestones" and current_user.role and current_user.role.name == "TEAM_LEAD":
            if not data or set(data) != {"is_completed"}:
                raise HTTPException(status_code=403, detail="Team Leads may update only milestone completion status")

        # A notification owner may only mark their own notification as read.
        if resource_name == "notifications":
            if obj.user_id != current_user.id or not data or set(data) != {"is_read"}:
                raise HTTPException(status_code=403, detail="You may only mark your own notifications as read")

        old_status = getattr(obj, "status", None)
        old_assignee = getattr(obj, "assignee_id", None)
        for key, value in data.items():
            setattr(obj, key, value)
        if resource_name == "tasks" and "status" in data:
            if data["status"] == "DONE" and old_status != "DONE":
                obj.completed_by = current_user.id
                obj.completed_at = datetime.now(timezone.utc)
            elif data["status"] != "DONE":
                obj.completed_by = None
                obj.completed_at = None
        if resource_name == "projects" and "status" in data:
            if data["status"] == "COMPLETED" and old_status != "COMPLETED":
                obj.completed_by = current_user.id
                obj.completed_at = datetime.now(timezone.utc)
            elif data["status"] != "COMPLETED":
                obj.completed_by = None
                obj.completed_at = None

        if resource_name == "tasks" and "status" in data and data["status"] != old_status:
            db.add(TaskStatusHistory(task_id=obj.id, changed_by=current_user.id, old_status=old_status, new_status=obj.status))

        try:
            db.commit()
            db.refresh(obj)

            if resource_name in {"projects", "tasks"}:
                kind = resource_name[:-1].upper()
                db.add(AuditLog(user_id=current_user.id, action=f"{kind}_UPDATED", entity_type=kind, entity_id=obj.id, details=f"Updated {getattr(obj, 'name', getattr(obj, 'title', kind))}; fields: {', '.join(data.keys())}"))
            if resource_name == "tasks":
                if data.get("assignee_id") and data.get("assignee_id") != old_assignee:
                    db.add(Notification(user_id=data["assignee_id"], title="Task assigned", message=f"You were assigned: {obj.title}", is_read=False))
                if "status" in data and data["status"] != old_status:
                    db.add(AuditLog(user_id=current_user.id, action="TASK_STATUS_UPDATED", entity_type="TASK", entity_id=obj.id, details=f"Status changed from {old_status} to {obj.status}"))
                    recipients = {obj.assignee_id, obj.project.owner_id} - {None, current_user.id}
                    recipients.update(db.scalars(select(ProjectMember.user_id).where(ProjectMember.project_id == obj.project_id, ProjectMember.project_role.in_(["LEAD", "TEAM_LEAD", "TL"]))).all())
                    for uid in recipients - {current_user.id}:
                        db.add(Notification(user_id=uid, title="Task status updated", message=f"{obj.title}: {old_status} → {obj.status}", is_read=False))
                if data.get("assignee_id") and data.get("assignee_id") != old_assignee:
                    db.add(AuditLog(user_id=current_user.id, action="TASK_ASSIGNED", entity_type="TASK", entity_id=obj.id, details=f"Assigned task to user #{obj.assignee_id}"))
            if resource_name == "projects" and data:
                if "status" in data and data["status"] != old_status:
                    db.add(AuditLog(user_id=current_user.id, action="PROJECT_STATUS_UPDATED", entity_type="PROJECT", entity_id=obj.id, details=f"Status changed from {old_status} to {obj.status}"))
                recipients = {m.user_id for m in obj.members} | {obj.owner_id}
                for uid in recipients - {current_user.id}:
                    db.add(Notification(user_id=uid, title="Project updated", message=f"{obj.name} was updated.", is_read=False))
            db.commit()
            return _serialize(obj)

        except IntegrityError as exc:
            db.rollback()

            print("\n========== DATABASE ERROR ==========")
            print(exc.orig)
            print("====================================\n")

            raise HTTPException(
                status_code=409,
                detail=str(exc.orig),
            ) from exc

    # DELETE ITEM

    def delete_item(
        item_id: int,
        db: Session = Depends(get_db),
        current_user = Depends(get_current_user),
    ):
        obj = db.scalar(_tenant_statement(select(model).where(model.id == item_id), resource_name, current_user))

        if obj is None:
            raise HTTPException(
                status_code=404,
                detail=f"{model.__name__} not found",
            )

        # Project Managers may delete only projects where they are the owner.
        if resource_name == "projects" and _is_project_manager(current_user) and obj.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can delete only projects you own")

        if _is_employee(current_user) and resource_name in {"projects", "tasks"}:
            if resource_name == "projects":
                allowed = db.scalar(select(Project.id).where(
                    Project.id == item_id,
                    or_(
                        Project.id.in_(select(ProjectMember.project_id).where(ProjectMember.user_id == current_user.id)),
                        Project.id.in_(select(Task.project_id).where(Task.assignee_id == current_user.id)),
                    ),
                )) is not None
            else:
                allowed = obj.assignee_id == current_user.id
            if not allowed:
                raise HTTPException(status_code=404, detail=f"{model.__name__} not found")

        db.delete(obj)

        try:
            db.commit()

            return {
                "message": f"{resource_name} record {item_id} deleted"
            }

        except IntegrityError as exc:
            db.rollback()

            print("\n========== DATABASE ERROR ==========")
            print(exc.orig)
            print("====================================\n")

            raise HTTPException(
                status_code=409,
                detail=str(exc.orig),
            ) from exc

    # ROUTE NAMES

    create_item.__name__ = f"create_{resource_name}"
    create_item.__annotations__["payload"] = CreateSchema

    update_item.__name__ = f"update_{resource_name}_item"
    update_item.__annotations__["payload"] = UpdateSchema

    list_items.__name__ = f"list_{resource_name}"
    get_item.__name__ = f"get_{resource_name}_item"
    delete_item.__name__ = f"delete_{resource_name}_item"

    # GET ALL

    router.add_api_route(
        base_path,
        list_items,
        methods=["GET"],
        name=list_items.__name__,
        response_model=list[ResponseSchema],
        tags=[tag],
        dependencies=[
            Depends(
                require_permission(
                    RESOURCE_PERMISSIONS[resource_name]["GET"]
                )
            )
        ],
    )

    # CREATE

    router.add_api_route(
        base_path,
        create_item,
        methods=["POST"],
        name=create_item.__name__,
        status_code=201,
        response_model=ResponseSchema,
        tags=[tag],
        dependencies=[
            Depends(
                require_permission(
                    RESOURCE_PERMISSIONS[resource_name]["POST"]
                )
            )
        ],
    )

    # GET BY ID

    router.add_api_route(
        base_path + "/{item_id}",
        get_item,
        methods=["GET"],
        name=get_item.__name__,
        response_model=ResponseSchema,
        tags=[tag],
        dependencies=[
            Depends(
                require_permission(
                    RESOURCE_PERMISSIONS[resource_name]["GET"]
                )
            )
        ],
    )

    # UPDATE

    router.add_api_route(
        base_path + "/{item_id}",
        update_item,
        methods=["PATCH"],
        name=update_item.__name__,
        response_model=ResponseSchema,
        tags=[tag],
        dependencies=[
            Depends(
                require_permission(
                    RESOURCE_PERMISSIONS[resource_name]["PATCH"]
                )
            )
        ],
    )

    # DELETE

    router.add_api_route(
        base_path + "/{item_id}",
        delete_item,
        methods=["DELETE"],
        name=delete_item.__name__,
        tags=[tag],
        dependencies=[
            Depends(
                require_permission(
                    RESOURCE_PERMISSIONS[resource_name]["DELETE"]
                )
            )
        ],
    )


# REGISTER ALL RESOURCES

for resource_name, model in RESOURCE_MODELS.items():
    register_resource(resource_name, model)
