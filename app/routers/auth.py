
from datetime import timedelta

import jwt

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import (
    User,
    Role,
    Permission,
    RolePermission, Company
)

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token
)

from app.core.config import settings

from app.schemas.auth import (
    UserRegister,
    UserLogin,
    UserResponse,
    TokenResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest
)



router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


# HTTP Bearer Authentication
bearer_scheme = HTTPBearer(auto_error=False)


# --------------------------------------------------
# REGISTER API
# --------------------------------------------------

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register_user(
    payload: UserRegister,
    db: Session = Depends(get_db)
):

    # Check email already exists
    existing_user = db.scalar(
        select(User).where(User.email == payload.email)
    )

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email already registered"
        )

    # Get default Employee role
    employee_role = db.scalar(
        select(Role).where(Role.name == "EMPLOYEE")
    )

    if not employee_role:
        raise HTTPException(
            status_code=500,
            detail="EMPLOYEE role not found in database"
        )

    # Create user
    company = db.scalar(select(Company).where(Company.company_code == payload.company_code.upper(), Company.is_active == True))
    if not company:
        raise HTTPException(status_code=404, detail="Company not found or inactive")
    employee_prefix = "emp" + "".join(ch for ch in company.company_code if ch.isalpha())[:3] + "e"
    count = db.scalar(select(func.count(User.id)).where(User.company_id == company.id, User.role_id == employee_role.id)) or 0
    employee_code = f"{employee_prefix}{count+1:03d}"
    user = User(
        company_id=company.id,
        employee_code=employee_code,
        full_name=payload.full_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role_id=employee_role.id,
        is_active=True
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Unable to register user"
        )

    return user


# --------------------------------------------------
# LOGIN API
# --------------------------------------------------

@router.post(
    "/login",
    response_model=TokenResponse
)
def login_user(
    payload: UserLogin,
    db: Session = Depends(get_db)
):

    # Find user using email
    stmt = select(User).where(User.email == payload.email)
    if payload.company_code:
        stmt = stmt.join(Company, Company.id == User.company_id).where(Company.company_code == payload.company_code.upper())
    user = db.scalar(stmt)

    # Verify email and password
    if not user or not verify_password(
        payload.password,
        user.password_hash
    ):

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Check account status
    if not user.is_active:

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )

    # Generate JWT token
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "company_id": user.company_id
        },
        expires_delta=timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


# --------------------------------------------------
# GET CURRENT USER - TOKEN VERIFICATION
# --------------------------------------------------

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db)
):

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:

        token = credentials.credentials

        # Decode JWT token
        payload = decode_access_token(token)

        # Get user ID from token
        user_id = int(payload.get("sub"))

    except (
        jwt.PyJWTError,
        TypeError,
        ValueError,
        AttributeError
    ):

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Find user in database
    user = db.get(User, user_id)

    if not user or not user.is_active:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    return user



# --------------------------------------------------
# FORGOT PASSWORD (DEVELOPMENT TOKEN FLOW)
# --------------------------------------------------

@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Generate a short-lived reset token; no SMTP/email delivery is used."""
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not user.is_active:
        return {"message": "If the account exists, a password reset request has been created."}

    reset_token = create_access_token(
        data={"sub": str(user.id), "purpose": "password_reset", "pwd": user.password_hash},
        expires_delta=timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    )
    response = {
        "message": "Password reset token generated. Use it in the Reset Password form.",
        "expires_in_minutes": settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    }
    if settings.RESET_TOKEN_EXPOSE:
        response["reset_token"] = reset_token
    return response


# --------------------------------------------------
# RESET PASSWORD
# --------------------------------------------------

@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        claims = decode_access_token(payload.token)
        if claims.get("purpose") != "password_reset":
            raise ValueError("Wrong token purpose")
        user_id = int(claims.get("sub"))
        token_password_hash = claims.get("pwd")
    except (jwt.PyJWTError, TypeError, ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid or expired password reset token")

    user = db.get(User, user_id)
    if not user or not user.is_active or not token_password_hash or token_password_hash != user.password_hash:
        raise HTTPException(status_code=400, detail="Invalid, expired, or already used password reset token")

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password has been reset successfully. Please sign in with your new password."}


# --------------------------------------------------
# CURRENT USER PROFILE API
# --------------------------------------------------

@router.get(
    "/me",
    response_model=UserResponse
)
def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Role-specific serial number within the same company, ordered by user ID.
    role_serial_id = db.scalar(
        select(func.count(User.id)).where(
            User.company_id == current_user.company_id,
            User.role_id == current_user.role_id,
            User.id <= current_user.id
        )
    ) or 1
    return {
        "id": current_user.id,
        "company_id": current_user.company_id,
        "employee_code": current_user.employee_code,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "department_id": current_user.department_id,
        "role_id": current_user.role_id,
        "role_serial_id": role_serial_id,
        "is_active": current_user.is_active,
    }



# --------------------------------------------------
# PERMISSION VERIFICATION
# --------------------------------------------------

def require_permission(permission_code: str):

    def permission_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):

        permission_exists = db.scalar(
            select(Permission.id)
            .join(
                RolePermission,
                RolePermission.permission_id == Permission.id
            )
            .where(
                RolePermission.role_id == current_user.role_id,
                Permission.code == permission_code
            )
        )

        if permission_exists is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission_code} required"
            )

        return current_user

    return permission_checker