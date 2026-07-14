"""Regression: ensure_schema repairs databases created before model columns
were added (e.g. the entities/splits work adding transactions.entity_id)."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import ensure_schema
from app.models import Category, ManualActual, Transaction


def _old_transactions_engine(tmp_path):
    """A pre-entity-migration DB: transactions table without the newer columns."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'old.db'}",
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY, plaid_txn_id VARCHAR, account_id INTEGER NOT NULL,
                import_source_id INTEGER, amount FLOAT NOT NULL, currency VARCHAR,
                date DATE NOT NULL, name VARCHAR NOT NULL, merchant_name VARCHAR,
                category_id INTEGER, pending BOOLEAN, review_status VARCHAR,
                review_source VARCHAR, confidence FLOAT, source_file VARCHAR,
                source_page INTEGER, dedup_hash VARCHAR, notes TEXT, created_at DATETIME
            )
            """
        ))
        conn.execute(text(
            "INSERT INTO transactions (account_id, amount, date, name, review_status) "
            "VALUES (1, 42.0, '2026-06-01', 'Test', 'confirmed')"
        ))
    return engine


def test_ensure_schema_adds_missing_columns(tmp_path):
    engine = _old_transactions_engine(tmp_path)
    # Sanity: the pre-migration DB is missing the entity columns.
    with engine.connect() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(transactions)"))}
    assert "entity_id" not in cols

    ensure_schema(engine)

    # Querying the ORM model (which references the new columns) now works.
    session = sessionmaker(bind=engine)()
    rows = session.query(Transaction).filter(Transaction.review_status == "confirmed").all()
    assert len(rows) == 1
    assert rows[0].entity_id is None
    assert rows[0].txn_type == "expense"  # default backfilled for existing row
    session.close()


def test_ensure_schema_is_idempotent(tmp_path):
    engine = _old_transactions_engine(tmp_path)
    ensure_schema(engine)
    ensure_schema(engine)  # must not raise on the already-repaired DB
    session = sessionmaker(bind=engine)()
    assert session.query(Transaction).count() == 1
    session.close()


def test_ensure_schema_creates_missing_tables(tmp_path):
    engine = _old_transactions_engine(tmp_path)
    ensure_schema(engine)
    from sqlalchemy import inspect

    tables = set(inspect(engine).get_table_names())
    # New tables introduced alongside the transaction columns are created too.
    assert {"entities", "transaction_splits", "entity_rules", "saved_views"} <= tables


def test_ensure_schema_adds_category_kind_and_manual_actuals(tmp_path):
    """A pre-manual-actuals DB: categories without `kind`, no manual_actuals."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'old.db'}",
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE categories ("
            "id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, parent_id INTEGER, "
            "icon VARCHAR, color VARCHAR, is_system BOOLEAN, created_at DATETIME)"
        ))
        conn.execute(text("INSERT INTO categories (name) VALUES ('Groceries')"))

    ensure_schema(engine)

    session = sessionmaker(bind=engine)()
    # Existing row survives and is backfilled to 'expense'.
    cat = session.query(Category).filter(Category.name == "Groceries").one()
    assert cat.kind == "expense"
    # New manual_actuals table is usable.
    session.add(ManualActual(category_id=cat.id, year_month="2026-07", amount=100.0))
    session.commit()
    assert session.query(ManualActual).count() == 1
    session.close()
