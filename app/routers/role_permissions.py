
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import (
    Role,
    Permission,
    RolePermission,
    User
)
from app.routers.users import get_current_admin
from app.schemas.role_permission import (
    RolePermissionCreate,
    RolePermissionResponse
)

router = APIRouter(
    prefix="/role-permissions",
    tags=["Role Permissions"]
)


# GET all role-permission assignments
@router.get("/", response_model=list[RolePermissionResponse])
def list_role_permissions(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    return db.scalars(
        select(RolePermission).order_by(RolePermission.id)
    ).all()


# GET permissions assigned to a specific role
@router.get("/role/{role_id}")
def get_role_permissions(
    role_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    role = db.get(Role, role_id)

    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    assignments = db.scalars(
        select(RolePermission).where(
            RolePermission.role_id == role_id
        )
    ).all()

    return [
        {
            "id": item.id,
            "role_id": item.role_id,
            "permission_id": item.permission_id,
            "permission_code": item.permission.code
        }
        for item in assignments
    ]


# ASSIGN permission to role
@router.post(
    "/",
    response_model=RolePermissionResponse,
    status_code=status.HTTP_201_CREATED
)
def assign_permission(
    payload: RolePermissionCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    role = db.get(Role, payload.role_id)

    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    permission = db.get(Permission, payload.permission_id)

    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")

    existing = db.scalar(
        select(RolePermission).where(
            RolePermission.role_id == payload.role_id,
            RolePermission.permission_id == payload.permission_id
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Permission already assigned to this role"
        )

    assignment = RolePermission(
        role_id=payload.role_id,
        permission_id=payload.permission_id
    )

    db.add(assignment)

    try:
        db.commit()
        db.refresh(assignment)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to assign permission"
        )

    return assignment


# REMOVE permission from role
@router.delete("/{assignment_id}")
def remove_permission(
    assignment_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    assignment = db.get(RolePermission, assignment_id)

    if not assignment:
        raise HTTPException(
            status_code=404,
            detail="Role permission assignment not found"
        )

    db.delete(assignment)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to remove permission"
        )

    return {"message": "Permission removed successfully"}
