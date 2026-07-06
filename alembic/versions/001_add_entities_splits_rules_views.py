"""Add entities, transaction_splits, entity_rules, saved_views; extend transactions.

Revision ID: 001
Revises:
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- entities ---
    op.create_table(
        "entities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, unique=True, nullable=False),
        sa.Column("entity_type", sa.String, nullable=False),
        sa.Column("color", sa.String, nullable=True),
        sa.Column("icon", sa.String, nullable=True),
        sa.Column("is_default", sa.Boolean, default=False),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, default=datetime.utcnow),
    )

    # --- transaction_splits ---
    op.create_table(
        "transaction_splits",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("transaction_id", sa.Integer, sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("entity_id", sa.Integer, sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("percent", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_transaction_splits_entity_id", "transaction_splits", ["entity_id"])

    # --- entity_rules ---
    op.create_table(
        "entity_rules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entity_id", sa.Integer, sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("field", sa.String, nullable=False),
        sa.Column("operator", sa.String, nullable=False),
        sa.Column("value", sa.String, nullable=False),
        sa.Column("priority", sa.Integer, default=100),
        sa.Column("is_active", sa.Boolean, default=True),
    )

    # --- saved_views ---
    op.create_table(
        "saved_views",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, unique=True, nullable=False),
        sa.Column("config", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, default=datetime.utcnow),
    )

    # --- add columns to transactions (batch mode for SQLite) ---
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("entity_id", sa.Integer, sa.ForeignKey("entities.id"), nullable=True))
        batch_op.add_column(sa.Column("txn_type", sa.String, server_default="expense"))
        batch_op.add_column(sa.Column("entity_source", sa.String, nullable=True))

    op.create_index("ix_transactions_entity_date", "transactions", ["entity_id", "date"])
    op.create_index("ix_transactions_date", "transactions", ["date"])

    # --- seed entities: House (default) and Airbnb ---
    entities_table = sa.table(
        "entities",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("entity_type", sa.String),
        sa.column("is_default", sa.Boolean),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
    )
    op.bulk_insert(entities_table, [
        {"id": 1, "name": "House", "entity_type": "household", "is_default": True, "is_active": True, "created_at": datetime.utcnow()},
        {"id": 2, "name": "Airbnb", "entity_type": "rental", "is_default": False, "is_active": True, "created_at": datetime.utcnow()},
    ])

    # --- backfill: assign all existing transactions to House (default entity) ---
    op.execute("UPDATE transactions SET entity_id = 1, entity_source = 'default' WHERE entity_id IS NULL")

    # --- seed saved views ---
    saved_views_table = sa.table(
        "saved_views",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("config", sa.Text),
        sa.column("created_at", sa.DateTime),
    )
    import json
    op.bulk_insert(saved_views_table, [
        {
            "id": 1,
            "name": "House — this month",
            "config": json.dumps({"filters": {"entity_id": 1, "date_range": "this_month"}, "sort": [{"field": "date", "dir": "desc"}]}),
            "created_at": datetime.utcnow(),
        },
        {
            "id": 2,
            "name": "Airbnb — this month",
            "config": json.dumps({"filters": {"entity_id": 2, "date_range": "this_month"}, "sort": [{"field": "date", "dir": "desc"}]}),
            "created_at": datetime.utcnow(),
        },
    ])


def downgrade() -> None:
    op.execute("DELETE FROM saved_views WHERE id IN (1, 2)")
    op.execute("DELETE FROM transactions WHERE entity_source IS NOT NULL")  # can't un-backfill cleanly
    op.drop_index("ix_transactions_date", table_name="transactions")
    op.drop_index("ix_transactions_entity_date", table_name="transactions")

    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("entity_source")
        batch_op.drop_column("txn_type")
        batch_op.drop_column("entity_id")

    op.drop_table("saved_views")
    op.drop_table("entity_rules")
    op.drop_table("transaction_splits")
    op.drop_table("entities")
