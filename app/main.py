
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.routers.all_resources import router as resources_router
from app.routers.auth import router as auth_router
from app.routers.auth import get_current_user
from app.routers.users import router as users_router
from app.routers.permission import router as permissions_router
from app.routers.role_permissions import router as role_permissions_router
from app.routers.analytics import router as analytics_router
from app.routers.chat import router as chat_router
from app.routers.task_options import router as task_options_router
from app.routers.companies import router as companies_router
from app.routers.completed_work import router as completed_work_router
from app.database import Base, engine
import app.models.entities  # register all SQLAlchemy models

app = FastAPI(
    title="Enterprise Project Management API",
    version="2.0.0",
    description="Multi-company project, task, team and workflow management backend with tenant-specific users and projects."
)


# CORS for the separately served frontend. Set FRONTEND_ORIGINS in production.
import os
_allowed_origins = [origin.strip() for origin in os.getenv(
    "FRONTEND_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:8000,http://localhost:8000"
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.on_event("startup")
def create_feature_tables():
    # Create new feature tables and additive completion metadata without dropping data.
    Base.metadata.create_all(bind=engine)
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS completed_by INTEGER REFERENCES users(id) ON DELETE SET NULL"))
        conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS completed_by INTEGER REFERENCES users(id) ON DELETE SET NULL"))
        conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ"))

# Health API
@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


# Authentication APIs
app.include_router(auth_router, prefix="/api/v1")
app.include_router(companies_router, prefix="/api/v1")


# User Management APIs
app.include_router(users_router, prefix="/api/v1")

app.include_router(permissions_router, prefix="/api/v1")

app.include_router(role_permissions_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(task_options_router, prefix="/api/v1")
app.include_router(completed_work_router, prefix="/api/v1")

# Other protected CRUD APIs
app.include_router(
    resources_router,
    prefix="/api/v1",
    dependencies=[Depends(get_current_user)]
)
