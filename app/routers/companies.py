from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.entities import Company, User, Role
from app.core.security import hash_password
from app.routers.auth import get_current_user

router = APIRouter(prefix="/companies", tags=["Companies"])

class CompanyRegister(BaseModel):
    company_name: str = Field(min_length=2, max_length=160)
    company_code: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9]+$")
    admin_full_name: str = Field(min_length=2, max_length=120)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=128)

@router.post("/register", status_code=201)
def register_company(payload: CompanyRegister, db: Session = Depends(get_db)):
    code = payload.company_code.upper()
    company_count = db.scalar(select(func.count(Company.id))) or 0
    if company_count >= 3:
        raise HTTPException(409, "This EPMS installation supports a maximum of 3 companies")
    if db.scalar(select(Company.id).where(Company.company_code == code)):
        raise HTTPException(409, "Company code already exists")
    if db.scalar(select(User.id).where(User.email == payload.admin_email)):
        raise HTTPException(409, "Admin email already registered")
    admin_role = db.scalar(select(Role).where(Role.name == "ADMIN"))
    if not admin_role:
        raise HTTPException(500, "ADMIN role not found. Seed roles first.")
    company = Company(company_name=payload.company_name.strip(), company_code=code, is_active=True)
    db.add(company)
    try:
        db.flush()
        admin = User(company_id=company.id, employee_code=f"admin{''.join(ch for ch in code if ch.isalpha())[:3].upper()}a001", full_name=payload.admin_full_name.strip(), email=payload.admin_email, password_hash=hash_password(payload.admin_password), role_id=admin_role.id, is_active=True)
        db.add(admin)
        db.commit()
        db.refresh(company)
        db.refresh(admin)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Company or Admin details already exist")
    return {"company_id": company.id, "company_name": company.company_name, "company_code": company.company_code, "admin_user_id": admin.id, "admin_employee_code": admin.employee_code, "message": "Company and Admin account created"}

@router.get("/me")
def my_company(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = db.get(Company, user.company_id)
    return {"id": company.id, "company_name": company.company_name, "company_code": company.company_code}
