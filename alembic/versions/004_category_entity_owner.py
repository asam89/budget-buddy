"""Give each category (income/expense line) an optional owning entity.

Adds nullable ``entity_id`` (FK -> entities.id) to ``categories``. NULL means
the line is shared across every entity (the default for existing categories, so
nothing changes for current data); a concrete value scopes the line to one
business so it only appears under that business.

Revision ID: 004
Revises: 003
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column("entity_id", sa.Integer, sa.ForeignKey("entities.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("categories", "entity_id")
