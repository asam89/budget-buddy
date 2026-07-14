import logging
import os

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _column_default_sql(col) -> str | None:
    """Render a column's Python/server default as a SQLite literal, if simple.

    Only scalar literals are handled; callable defaults (e.g. datetime.utcnow)
    are skipped so we don't inject invalid SQL.
    """
    default = col.default
    if default is not None and getattr(default, "is_scalar", False):
        val = default.arg
        if isinstance(val, bool):
            return "1" if val else "0"
        if isinstance(val, (int, float)):
            return str(val)
        if isinstance(val, str):
            escaped = val.replace("'", "''")
            return f"'{escaped}'"
    server_default = col.server_default
    if server_default is not None and hasattr(server_default, "arg"):
        arg = server_default.arg
        return arg if isinstance(arg, str) else str(arg)
    return None


def ensure_schema(engine: Engine) -> None:
    """Bring an existing database up to the current models, idempotently.

    ``Base.metadata.create_all`` creates missing tables but never alters an
    existing one, so a database created before a model added columns (e.g. the
    entities/splits work added ``transactions.entity_id``) is missing those
    columns and every query against the table fails with ``no such column``.
    Here we create any missing tables, then ``ALTER TABLE ... ADD COLUMN`` for
    any model column absent from an existing table. Columns are added nullable
    (SQLite forbids adding a NOT NULL column without a default to a populated
    table), with a literal default applied when the model defines one.
    """
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            db_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in db_cols:
                    continue
                coltype = col.type.compile(dialect=engine.dialect)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'
                default_sql = _column_default_sql(col)
                if default_sql is not None:
                    ddl += f" DEFAULT {default_sql}"
                try:
                    conn.execute(text(ddl))
                    logger.info("Schema repair: added %s.%s", table.name, col.name)
                except Exception:
                    logger.exception(
                        "Schema repair: could not add %s.%s", table.name, col.name
                    )


def _create_engine():
    settings = get_settings()
    db_path = os.path.abspath(settings.database_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    db_url = f"sqlite+pysqlcipher://:{settings.db_passphrase}@/{db_path}"

    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
    )
    return engine


engine = _create_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
