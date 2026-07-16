"""Startup data migration for entity-scoped budgets and manual actuals.

``ensure_schema`` adds the new nullable ``entity_id`` columns to existing
databases, but two things it can't do are handled here, idempotently, on every
startup (deploy runs the app, not Alembic):

1. Backfill legacy rows (``entity_id IS NULL``) to the default entity so the
   Personal view keeps every pre-entity budget/manual actual.
2. Rebuild ``manual_actuals`` when it still carries the old
   ``UNIQUE(category_id, year_month)`` constraint, which would block a second
   entity from having its own value for the same category+month. The rebuild
   copies every row, so it is zero-data-loss and verified by row count.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.services.entity_seed import DEFAULT_ENTITY_NAME

logger = logging.getLogger(__name__)

_NEW_UQ = "uq_manual_actual_category_month_entity"


def _default_entity_id(conn) -> int | None:
    row = conn.execute(
        text("SELECT id FROM entities WHERE is_default = 1 ORDER BY id LIMIT 1")
    ).fetchone()
    if row is not None:
        return row[0]
    row = conn.execute(
        text("SELECT id FROM entities WHERE name = :n ORDER BY id LIMIT 1"),
        {"n": DEFAULT_ENTITY_NAME},
    ).fetchone()
    return row[0] if row is not None else None


def _has_column(inspector, table: str, column: str) -> bool:
    try:
        return any(c["name"] == column for c in inspector.get_columns(table))
    except Exception:
        return False


def _backfill_entity(conn, table: str, default_id: int) -> None:
    conn.execute(
        text(f"UPDATE {table} SET entity_id = :eid WHERE entity_id IS NULL"),
        {"eid": default_id},
    )


def _rebuild_manual_actuals(conn) -> None:
    """Recreate manual_actuals with the entity-aware unique constraint."""
    before = conn.execute(text("SELECT COUNT(*) FROM manual_actuals")).scalar()
    conn.execute(text(
        """
        CREATE TABLE manual_actuals_new (
            id INTEGER PRIMARY KEY,
            category_id INTEGER NOT NULL REFERENCES categories(id),
            entity_id INTEGER REFERENCES entities(id),
            year_month VARCHAR NOT NULL,
            amount FLOAT NOT NULL,
            note TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            CONSTRAINT uq_manual_actual_category_month_entity
                UNIQUE (category_id, year_month, entity_id)
        )
        """
    ))
    conn.execute(text(
        """
        INSERT INTO manual_actuals_new
            (id, category_id, entity_id, year_month, amount, note, created_at, updated_at)
        SELECT id, category_id, entity_id, year_month, amount, note, created_at, updated_at
        FROM manual_actuals
        """
    ))
    after = conn.execute(text("SELECT COUNT(*) FROM manual_actuals_new")).scalar()
    if after != before:
        raise RuntimeError(
            f"manual_actuals rebuild row mismatch: {before} -> {after}; aborting"
        )
    conn.execute(text("DROP TABLE manual_actuals"))
    conn.execute(text("ALTER TABLE manual_actuals_new RENAME TO manual_actuals"))
    logger.info("Schema repair: rebuilt manual_actuals with entity-scoped unique constraint")


def migrate_entity_scoping(engine: Engine) -> None:
    """Idempotently scope budgets/manual_actuals to entities on an existing DB."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "entities" not in tables:
        return

    with engine.begin() as conn:
        default_id = _default_entity_id(conn)
        if default_id is None:
            return  # seeding hasn't produced a default yet

        if "budgets" in tables and _has_column(inspector, "budgets", "entity_id"):
            _backfill_entity(conn, "budgets", default_id)

        if "manual_actuals" in tables and _has_column(inspector, "manual_actuals", "entity_id"):
            _backfill_entity(conn, "manual_actuals", default_id)
            create_sql = conn.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'manual_actuals'"
                )
            ).scalar()
            if create_sql and _NEW_UQ not in create_sql:
                _rebuild_manual_actuals(conn)
