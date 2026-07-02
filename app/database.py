import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


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
