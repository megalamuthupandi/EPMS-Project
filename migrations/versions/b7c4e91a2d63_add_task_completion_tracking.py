"""add task completion tracking fields (safe for partially updated databases)

Revision ID: b7c4e91a2d63
Revises: 9a71c2e5b4d8
Create Date: 2026-11-28
"""

from alembic import op
import sqlalchemy as sa

revision = "b7c4e91a2d63"
down_revision = "9a71c2e5b4d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Some installations already contain one or both columns. Add only what is missing.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("tasks")}

    if "completed_by" not in existing_columns:
        op.add_column("tasks", sa.Column("completed_by", sa.Integer(), nullable=True))

    if "completed_at" not in existing_columns:
        op.add_column("tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

    # Refresh FK metadata after column changes and avoid creating a duplicate FK.
    inspector = sa.inspect(bind)
    foreign_keys = inspector.get_foreign_keys("tasks")
    has_completed_by_fk = any(
        fk.get("constrained_columns") == ["completed_by"]
        and fk.get("referred_table") == "users"
        and fk.get("referred_columns") == ["id"]
        for fk in foreign_keys
    )
    if "completed_by" in {c["name"] for c in inspector.get_columns("tasks")} and not has_completed_by_fk:
        op.create_foreign_key(
            "fk_tasks_completed_by_users",
            "tasks",
            "users",
            ["completed_by"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    # Intentionally preserve completion columns: they may have existed before this
    # migration was applied, and dropping them could destroy existing task history.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys("tasks"):
        if (
            fk.get("name") == "fk_tasks_completed_by_users"
            and fk.get("constrained_columns") == ["completed_by"]
        ):
            op.drop_constraint("fk_tasks_completed_by_users", "tasks", type_="foreignkey")
            break
