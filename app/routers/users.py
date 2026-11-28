from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import User, Role
from app.core.security import hash_password
from app.routers.auth import get_current_user
from app.schemas.users import UserCreate, UserUpdate, UserResponse


router = APIRouter(prefix="/users", tags=["User Management"])


# ADMIN authentication and role verification
def get_current_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    role = db.get(Role, current_user.role_id)

    if not role or role.name.strip().upper() != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only ADMIN can access User Management"
        )

    return current_user


# GET all users
@router.get("/", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    users = db.scalars(select(User).where(User.company_id == admin.company_id).order_by(User.id)).all()
    return users


# GET user by ID
@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    user = db.scalar(select(User).where(User.id == user_id, User.company_id == admin.company_id))

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


# CREATE user
@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    existing_user = db.scalar(
        select(User).where(User.email == payload.email)
    )

    if existing_user:
        raise HTTPException(status_code=409, detail="Email already registered")

    role = db.get(Role, payload.role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.name.upper() == "ADMIN" and db.scalar(select(User.id).where(User.company_id == admin.company_id, User.role_id == role.id)):
        raise HTTPException(status_code=409, detail="This company already has an ADMIN account")

    if payload.department_id is not None:
        from app.models.entities import Department
        department = db.get(Department, payload.department_id)
        if not department:
            raise HTTPException(status_code=404, detail="Department not found")

    company_users = db.scalars(select(User).where(User.company_id == admin.company_id)).all()
    role_prefix = {"ADMIN": "admin", "PROJECT_MANAGER": "pm", "TEAM_LEAD": "tl", "EMPLOYEE": "emp"}.get(role.name.upper(), "usr")
    code_letter = {"ADMIN": "a", "PROJECT_MANAGER": "P", "TEAM_LEAD": "T", "EMPLOYEE": "e"}.get(role.name.upper(), "u")
    existing_numbers = []
    company_stem = "".join(ch for ch in admin.company.company_code if ch.isalpha())[:3].upper() or "ORG"
    prefix = f"{role_prefix}{company_stem}{code_letter}"
    for member in company_users:
        if member.employee_code.startswith(prefix):
            suffix = member.employee_code[len(prefix):]
            if suffix.isdigit(): existing_numbers.append(int(suffix))
    employee_code = f"{prefix}{max(existing_numbers, default=0)+1:03d}"

    user = User(
        company_id=admin.company_id,
        employee_code=employee_code,
        full_name=payload.full_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        department_id=payload.department_id,
        role_id=payload.role_id,
        is_active=True
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Unable to create user")

    return user


# UPDATE user
@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    user = db.scalar(select(User).where(User.id == user_id, User.company_id == admin.company_id))

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = payload.model_dump(exclude_unset=True)

    if "email" in update_data:
        existing_user = db.scalar(
            select(User).where(
                User.email == update_data["email"],
                User.id != user_id
            )
        )
        if existing_user:
            raise HTTPException(status_code=409, detail="Email already registered")

    if "role_id" in update_data:
        role = db.get(Role, update_data["role_id"])
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")

    if "department_id" in update_data and update_data["department_id"] is not None:
        from app.models.entities import Department
        department = db.get(Department, update_data["department_id"])
        if not department:
            raise HTTPException(status_code=404, detail="Department not found")

    for field, value in update_data.items():
        setattr(user, field, value)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Unable to update user")

    return user


# DELETE user
@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    user = db.scalar(select(User).where(User.id == user_id, User.company_id == admin.company_id))

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot delete your own ADMIN account"
        )

    db.delete(user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="User cannot be deleted because related records exist"
        )

    return {"message": "User deleted successfully"}