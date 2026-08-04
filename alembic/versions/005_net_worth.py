"""Add net worth tracking: assets, liabilities, net worth snapshots.

Introduces three tables backing the balance-sheet / net-worth view:
- ``assets``: manually-tracked assets (homes, businesses, investments, ...).
- ``liabilities``: manually-tracked debts (mortgages, loans, credit cards).
- ``net_worth_snapshots``: dated totals so net worth can be charted over time.

All are additive; existing data is untouched.

Revision ID: 005
Revises: 004
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("asset_class", sa.String, nullable=False, server_default="other"),
        sa.Column("value", sa.Float, nullable=False, server_default="0"),
        sa.Column("currency", sa.String, server_default="CAD"),
        sa.Column("entity_id", sa.Integer, sa.ForeignKey("entities.id"), nullable=True),
        sa.Column("institution", sa.String, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_assets_entity_id", "assets", ["entity_id"])

    op.create_table(
        "liabilities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("liability_class", sa.String, nullable=False, server_default="other"),
        sa.Column("balance", sa.Float, nullable=False, server_default="0"),
        sa.Column("currency", sa.String, server_default="CAD"),
        sa.Column("entity_id", sa.Integer, sa.ForeignKey("entities.id"), nullable=True),
        sa.Column("institution", sa.String, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_liabilities_entity_id", "liabilities", ["entity_id"])

    op.create_table(
        "net_worth_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("total_assets", sa.Float, nullable=False, server_default="0"),
        sa.Column("total_liabilities", sa.Float, nullable=False, server_default="0"),
        sa.Column("net_worth", sa.Float, nullable=False, server_default="0"),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_net_worth_snapshots_as_of", "net_worth_snapshots", ["as_of_date"])


def downgrade() -> None:
    op.drop_index("ix_net_worth_snapshots_as_of", table_name="net_worth_snapshots")
    op.drop_table("net_worth_snapshots")
    op.drop_index("ix_liabilities_entity_id", table_name="liabilities")
    op.drop_table("liabilities")
    op.drop_index("ix_assets_entity_id", table_name="assets")
    op.drop_table("assets")
