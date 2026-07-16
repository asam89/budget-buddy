"""Startup entity-scope migration: backfill + manual_actuals constraint rebuild.

Simulates a pre-entity-scope database (old manual_actuals unique constraint,
NULL entity_id rows) and verifies migrate_entity_scoping backfills to the
default entity and widens the unique constraint without losing rows.
"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.services.entity_scope_migration import migrate_entity_scoping


def _legacy_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'legacy.db'}",
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE entities (
                id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, entity_type VARCHAR,
                is_default BOOLEAN, is_active BOOLEAN
            )
        """))
        conn.execute(text("CREATE TABLE categories (id INTEGER PRIMARY KEY, name VARCHAR, kind VARCHAR)"))
        # Old manual_actuals: unique(category_id, year_month), NO entity_id yet.
        conn.execute(text("""
            CREATE TABLE manual_actuals (
                id INTEGER PRIMARY KEY,
                category_id INTEGER NOT NULL,
                year_month VARCHAR NOT NULL,
                amount FLOAT NOT NULL,
                note TEXT,
                created_at DATETIME,
                updated_at DATETIME,
                CONSTRAINT uq_manual_actual_category_month UNIQUE (category_id, year_month)
            )
        """))
        conn.execute(text("""
            CREATE TABLE budgets (
                id INTEGER PRIMARY KEY, category_id INTEGER NOT NULL,
                monthly_limit FLOAT, year_month VARCHAR, is_active BOOLEAN
            )
        """))
        conn.execute(text("INSERT INTO entities (id, name, entity_type, is_default, is_active) VALUES (1,'Personal','personal',1,1)"))
        conn.execute(text("INSERT INTO categories (id, name, kind) VALUES (1,'Groceries','expense')"))
        conn.execute(text("INSERT INTO manual_actuals (id, category_id, year_month, amount) VALUES (1,1,'2026-01',100)"))
        conn.execute(text("INSERT INTO budgets (id, category_id, monthly_limit, year_month, is_active) VALUES (1,1,500,NULL,1)"))
        # ensure_schema equivalent: add the nullable entity_id columns.
        conn.execute(text("ALTER TABLE manual_actuals ADD COLUMN entity_id INTEGER"))
        conn.execute(text("ALTER TABLE budgets ADD COLUMN entity_id INTEGER"))
    return engine


def test_backfill_and_rebuild(tmp_path):
    engine = _legacy_engine(tmp_path)

    migrate_entity_scoping(engine)

    with engine.begin() as conn:
        # Backfilled to the default entity (id 1).
        assert conn.execute(text("SELECT entity_id FROM manual_actuals WHERE id=1")).scalar() == 1
        assert conn.execute(text("SELECT entity_id FROM budgets WHERE id=1")).scalar() == 1
        # No rows lost.
        assert conn.execute(text("SELECT COUNT(*) FROM manual_actuals")).scalar() == 1
        # New unique constraint in place.
        create_sql = conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='manual_actuals'"
        )).scalar()
        assert "uq_manual_actual_category_month_entity" in create_sql
        # A second entity can now hold the same (category, month).
        conn.execute(text(
            "INSERT INTO manual_actuals (category_id, year_month, amount, entity_id) VALUES (1,'2026-01',7,2)"
        ))


def test_migration_is_idempotent(tmp_path):
    engine = _legacy_engine(tmp_path)
    migrate_entity_scoping(engine)
    migrate_entity_scoping(engine)  # second run must be a no-op, not raise

    with engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM manual_actuals")).scalar() == 1
