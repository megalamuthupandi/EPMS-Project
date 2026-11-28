
"""add multi-company tenancy and company-specific employee codes

Revision ID: 9a71c2e5b4d8
Revises: 4c8fd8b7f5fb
"""

from alembic import op
import sqlalchemy as sa

revision = "9a71c2e5b4d8"
down_revision = "4c8fd8b7f5fb"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # companies table already exists. Do not recreate it.
    # Its company_code unique index also already exists.

    op.add_column(
        "users",
        sa.Column("company_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("employee_code", sa.String(length=80), nullable=True)
    )
    op.add_column(
        "projects",
        sa.Column("company_id", sa.Integer(), nullable=True)
    )

    # Existing users/projects are empty, so no legacy workspace is needed.
    op.alter_column("users", "company_id", nullable=False)
    op.alter_column("users", "employee_code", nullable=False)
    op.alter_column("projects", "company_id", nullable=False)

    op.create_foreign_key(
        "fk_users_company_id_companies",
        "users",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="CASCADE"
    )
    op.create_foreign_key(
        "fk_projects_company_id_companies",
        "projects",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="CASCADE"
    )

    op.create_index("ix_users_company_id", "users", ["company_id"])
    op.create_index("ix_projects_company_id", "projects", ["company_id"])

    op.create_unique_constraint(
        "uq_users_company_employee_code",
        "users",
        ["company_id", "employee_code"]
    )
