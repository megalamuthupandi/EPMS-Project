"""add project completion tracking fields (safe for existing databases)

Revision ID: c8d5f2a1e6b9
Revises: b7c4e91a2d63
Create Date: 2026-11-28
"""
from alembic import op
import sqlalchemy as sa

revision = "c8d5f2a1e6b9"
down_revision = "b7c4e91a2d63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("projects")}

    if "completed_by" not in existing:
        op.add_column("projects", sa.Column("completed_by", sa.Integer(), nullable=True))
    if "completed_at" not in existing:
        op.add_column("projects", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

    inspector = sa.inspect(bind)
    fks = inspector.get_foreign_keys("projects")
    has_fk = any(
        fk.get("constrained_columns") == ["completed_by"]
        and fk.get("referred_table") == "users"
        and fk.get("referred_columns") == ["id"]
        for fk in fks
    )
    columns = {column["name"] for column in inspector.get_columns("projects")}
    if "completed_by" in columns and not has_fk:
        op.create_foreign_key(
            "fk_projects_completed_by_users", "projects", "users",
            ["completed_by"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    # Keep completion history during downgrade to avoid accidental data loss.
    pass
