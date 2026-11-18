"""Backup zip: restorable encrypted DB copy, readable workbook, no secrets."""

import io
import zipfile

import pytest
from openpyxl import load_workbook
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Category, PlaidItem, User
from app.services.backup import build_backup, copy_database, verify_copy

PASS = "0123456789abcdef0123456789abcdef"


def _seed(engine):
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    s.add_all([Category(name="Rent", kind="expense"), Category(name="Salary", kind="income"),
               User(username="admin", password_hash="$2b$secret-hash", is_active=True)])
    s.add(PlaidItem(item_id="item-1", access_token="access-sandbox-SECRET"))
    s.commit()
    s.close()


@pytest.fixture(params=["sqlcipher", "sqlite"])
def engine(request, tmp_path):
    if request.param == "sqlcipher":
        e = create_engine(f"sqlite+pysqlcipher://:{PASS}@/{tmp_path / 'live.db'}")
    else:
        e = create_engine(f"sqlite:///{tmp_path / 'live.db'}")
    _seed(e)
    yield e
    e.dispose()


def _open_zip(path):
    return zipfile.ZipFile(path)


def test_backup_zip_contents(engine, tmp_path):
    path = build_backup(engine, PASS, workdir=str(tmp_path))
    z = _open_zip(path)
    assert sorted(z.namelist()) == ["RESTORE.txt", "budget-buddy-data.xlsx", "budget_buddy.db"]

    restored = tmp_path / "restored.db"
    restored.write_bytes(z.read("budget_buddy.db"))
    counts = verify_copy(engine, str(restored), PASS)
    assert counts["categories"] == 2 and counts["plaid_items"] == 1

    wb = load_workbook(io.BytesIO(z.read("budget-buddy-data.xlsx")))
    names = {r[1] for r in wb["categories"].iter_rows(min_row=2, values_only=True)}
    assert {"Rent", "Salary"} <= names
    flat = " ".join(str(c) for ws in wb for row in ws.iter_rows(values_only=True) for c in row if c)
    assert "access-sandbox-SECRET" not in flat and "secret-hash" not in flat
    assert "access_token" not in [c.value for c in wb["plaid_items"][1]]
    assert "DB_PASSPHRASE" in z.read("RESTORE.txt").decode()


def test_encrypted_copy_needs_the_passphrase(tmp_path):
    e = create_engine(f"sqlite+pysqlcipher://:{PASS}@/{tmp_path / 'live.db'}")
    _seed(e)
    dest = tmp_path / "copy.db"
    copy_database(e, str(dest), PASS)
    assert b"SQLite format 3" not in dest.read_bytes()[:16]      # still encrypted
    wrong = create_engine(f"sqlite+pysqlcipher://:wrong-key@/{dest}")
    with pytest.raises(Exception):
        with wrong.connect() as c:
            c.execute(text("SELECT COUNT(*) FROM categories")).scalar()
    wrong.dispose()
    e.dispose()


def test_verify_detects_a_bad_copy(engine, tmp_path):
    dest = tmp_path / "copy.db"
    copy_database(engine, str(dest), PASS)
    with engine.begin() as c:
        c.execute(text("INSERT INTO categories (name, kind) VALUES ('Late', 'expense')"))
    with pytest.raises(RuntimeError, match="row counts differ"):
        verify_copy(engine, str(dest), PASS)


def test_download_endpoint(client, engine, monkeypatch, tmp_path):
    import app.routers.backup as backup_router
    monkeypatch.setattr(backup_router, "engine", engine)
    monkeypatch.setattr(backup_router, "get_settings", lambda: type("S", (), {"db_passphrase": PASS})())
    r = client.get("/api/backup/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "budget-buddy-backup-" in r.headers["content-disposition"]
    assert "budget_buddy.db" in zipfile.ZipFile(io.BytesIO(r.content)).namelist()
