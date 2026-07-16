"""Scope budgets and manual_actuals to entities.

Adds nullable ``entity_id`` (FK -> entities.id) to ``budgets`` and
``manual_actuals``, backfills existing rows to the default entity (falling back
to the one named "Personal"), and widens the manual_actuals unique constraint
to ``(category_id, year_month, entity_id)`` so each entity can hold its own
value for a category+month.

Revision ID: 003
Revises: 002
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def _default_entity_id(conn) -> int | None:
    row = conn.execute(
        sa.text("SELECT id FROM entities WHERE is_default = 1 ORDER BY id LIMIT 1")
    ).fetchone()
    if row is not None:
        return row[0]
    row = conn.execute(
        sa.text("SELECT id FROM entities WHERE name = 'Personal' ORDER BY id LIMIT 1")
    ).fetchone()
    return row[0] if row is not None else None


def upgrade() -> None:
    op.add_column("budgets", sa.Column("entity_id", sa.Integer, sa.ForeignKey("entities.id"), nullable=True))
    op.add_column("manual_actuals", sa.Column("entity_id", sa.Integer, sa.ForeignKey("entities.id"), nullable=True))

    conn = op.get_bind()
    default_id = _default_entity_id(conn)
    if default_id is not None:
        conn.execute(
            sa.text("UPDATE budgets SET entity_id = :eid WHERE entity_id IS NULL"),
            {"eid": default_id},
        )
        conn.execute(
            sa.text("UPDATE manual_actuals SET entity_id = :eid WHERE entity_id IS NULL"),
            {"eid": default_id},
        )

    # Widen the manual_actuals unique constraint to include entity_id.
    with op.batch_alter_table("manual_actuals", recreate="always") as batch:
        batch.drop_constraint("uq_manual_actual_category_month", type_="unique")
        batch.create_unique_constraint(
            "uq_manual_actual_category_month_entity",
            ["category_id", "year_month", "entity_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("manual_actuals", recreate="always") as batch:
        batch.drop_constraint("uq_manual_actual_category_month_entity", type_="unique")
        batch.create_unique_constraint(
            "uq_manual_actual_category_month",
            ["category_id", "year_month"],
        )
    op.drop_column("manual_actuals", "entity_id")
    op.drop_column("budgets", "entity_id")
