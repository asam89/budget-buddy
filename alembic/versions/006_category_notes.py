"""Give each category (income/expense line) a free-text note.

Adds nullable ``notes`` to ``categories`` so a line can carry context (renewal
date, which account pays it, why the budget is what it is) that is editable
straight from the grid row.

Revision ID: 006
Revises: 005
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("notes", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("categories", "notes")
