"""Add categories.kind and manual_actuals table.

Revision ID: 002
Revises: 001
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- categories.kind (backfill existing rows to 'expense') ---
    op.add_column(
        "categories",
        sa.Column("kind", sa.String, nullable=False, server_default="expense"),
    )

    # --- manual_actuals ---
    op.create_table(
        "manual_actuals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("year_month", sa.String, nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, default=datetime.utcnow),
        sa.Column("updated_at", sa.DateTime, default=datetime.utcnow),
        sa.UniqueConstraint("category_id", "year_month", name="uq_manual_actual_category_month"),
    )


def downgrade() -> None:
    op.drop_table("manual_actuals")
    op.drop_column("categories", "kind")
