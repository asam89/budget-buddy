import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool

from alembic import context

# Add project root to sys.path so app imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Base, engine  # noqa: E402
from app.models import (  # noqa: E402, F401 — import all models so metadata is populated
    Institution, PlaidItem, Account, Category, ImportSource,
    Entity, Transaction, TransactionSplit, EntityRule, SavedView,
    Budget, Bill, User, ManualActual,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emits SQL to stdout."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using the app's SQLCipher engine."""
    connectable = engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # required for SQLite ALTER TABLE support
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
