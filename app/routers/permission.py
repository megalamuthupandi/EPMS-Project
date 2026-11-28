
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Permission, User
from app.routers.users import get_current_admin
from app.schemas.permission import (
    PermissionCreate,
    PermissionUpdate,
    PermissionResponse
)

router = APIRouter(
    prefix="/permissions",
    tags=["Permissions"]
)


# GET all permissions
@router.get("/", response_model=list[PermissionResponse])
def list_permissions(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    return db.scalars(
        select(Permission).order_by(Permission.id)
    ).all()


# GET permission by ID
@router.get("/{permission_id}", response_model=PermissionResponse)
def get_permission(
    permission_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    permission = db.get(Permission, permission_id)

    if not permission:
        raise HTTPException(
            status_code=404,
            detail="Permission not found"
        )

    return permission


# CREATE permission
@router.post(
    "/",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED
)
def create_permission(
    payload: PermissionCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    existing = db.scalar(
        select(Permission).where(Permission.code == payload.code)
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Permission code already exists"
        )

    permission = Permission(
        code=payload.code,
        description=payload.description
    )

    db.add(permission)

    try:
        db.commit()
        db.refresh(permission)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to create permission"
        )

    return permission


# UPDATE permission
@router.patch("/{permission_id}", response_model=PermissionResponse)
def update_permission(
    permission_id: int,
    payload: PermissionUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    permission = db.get(Permission, permission_id)

    if not permission:
        raise HTTPException(
            status_code=404,
            detail="Permission not found"
        )

    update_data = payload.model_dump(exclude_unset=True)

    if "code" in update_data:
        existing = db.scalar(
            select(Permission).where(
                Permission.code == update_data["code"],
                Permission.id != permission_id
            )
        )

        if existing:
            raise HTTPException(
                status_code=409,
                detail="Permission code already exists"
            )

    for field, value in update_data.items():
        setattr(permission, field, value)

    try:
        db.commit()
        db.refresh(permission)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to update permission"
        )

    return permission


# DELETE permission
@router.delete("/{permission_id}")
def delete_permission(
    permission_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    permission = db.get(Permission, permission_id)

    if not permission:
        raise HTTPException(
            status_code=404,
            detail="Permission not found"
        )

    db.delete(permission)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Unable to delete permission"
        )

    return {"message": "Permission deleted successfully"}
