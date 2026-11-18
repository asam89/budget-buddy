"""One-click backup: a zip with a restorable database copy and a readable copy.

The zip holds:
  * ``budget_buddy.db``: a consistent copy of the live database, still
    encrypted with your DB_PASSPHRASE. Taken with SQLCipher's export (or
    ``VACUUM INTO`` on plain SQLite), so it's safe while the app is running.
    The copy is re-opened and its row counts checked before it's handed out.
  * ``budget-buddy-data.xlsx``: every table as a sheet, readable without the
    app. Secrets (Plaid access tokens, password hashes) are left out.
  * ``RESTORE.txt``: how to restore.
"""

import os
import re
import tempfile
import zipfile
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

SECRET_COLUMNS = re.compile(r"(access_token|password|secret|api_key)", re.I)
SHEET_ROW_LIMIT = 1_000_000

RESTORE_TEXT = """Budget Buddy backup, made {when}

budget_buddy.db
  A complete copy of your database. It is encrypted with the DB_PASSPHRASE
  from your .env, so keep that passphrase somewhere safe: without it this
  file can't be opened.

  To restore:
    1. Stop Budget Buddy (launchctl unload ~/Library/LaunchAgents/com.budgetbuddy.plist,
       or stop uvicorn).
    2. Move your current data/budget_buddy.db somewhere safe.
    3. Copy this budget_buddy.db into data/.
    4. Start Budget Buddy again with the same DB_PASSPHRASE.

budget-buddy-data.xlsx
  The same data as a spreadsheet, one sheet per table, readable without
  Budget Buddy. It is NOT encrypted, so store it somewhere private. Plaid
  access tokens and password hashes are left out.
"""


def _is_sqlcipher(engine: Engine) -> bool:
    return engine.dialect.driver == "pysqlcipher"


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def copy_database(engine: Engine, dest: str, passphrase: str | None) -> None:
    """Write a consistent copy of the live database to ``dest``."""
    if os.path.exists(dest):
        os.remove(dest)
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        if _is_sqlcipher(engine):
            # ATTACH can't take bound parameters for KEY; values are quoted.
            cur.execute(f"ATTACH DATABASE {_quote(dest)} AS backup KEY {_quote(passphrase or '')}")
            cur.execute("SELECT sqlcipher_export('backup')")
            cur.execute("DETACH DATABASE backup")
        else:
            cur.execute(f"VACUUM INTO {_quote(dest)}")
        cur.close()
    finally:
        raw.close()


def _backup_engine(engine: Engine, path: str, passphrase: str | None) -> Engine:
    if _is_sqlcipher(engine):
        return create_engine(f"sqlite+pysqlcipher://:{passphrase}@/{path}")
    return create_engine(f"sqlite:///{path}")


def _row_counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {t: conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
                for t in inspect(conn).get_table_names()}


def verify_copy(engine: Engine, path: str, passphrase: str | None) -> dict[str, int]:
    """Open the copy with the same key and check it has every table and row."""
    copy = _backup_engine(engine, path, passphrase)
    try:
        got = _row_counts(copy)
    finally:
        copy.dispose()
    want = _row_counts(engine)
    missing = {t: (n, got.get(t)) for t, n in want.items() if got.get(t) != n}
    if missing:
        raise RuntimeError(f"Backup check failed, table row counts differ: {missing}")
    return got


def readable_workbook(engine: Engine, dest: str) -> None:
    """Every table as a sheet, minus secret columns."""
    wb = Workbook(write_only=True)
    with engine.connect() as conn:
        for table in sorted(inspect(conn).get_table_names()):
            if table == "alembic_version":
                continue
            cols = [c["name"] for c in inspect(conn).get_columns(table)
                    if not SECRET_COLUMNS.search(c["name"])]
            ws = wb.create_sheet(table[:31])
            ws.append(cols)
            if not cols:
                continue
            col_sql = ", ".join(f'"{c}"' for c in cols)
            result = conn.execute(text(f'SELECT {col_sql} FROM "{table}" LIMIT {SHEET_ROW_LIMIT}'))
            for row in result:
                ws.append([v if isinstance(v, (int, float, str)) or v is None else str(v) for v in row])
    wb.save(dest)


def build_backup(engine: Engine, passphrase: str | None, workdir: str | None = None) -> str:
    """Create the backup zip and return its path. The caller deletes it."""
    work = tempfile.mkdtemp(prefix="bb-backup-", dir=workdir)
    db_copy = os.path.join(work, "budget_buddy.db")
    xlsx = os.path.join(work, "budget-buddy-data.xlsx")
    copy_database(engine, db_copy, passphrase)
    verify_copy(engine, db_copy, passphrase)
    readable_workbook(engine, xlsx)

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    zip_path = os.path.join(work, f"budget-buddy-backup-{stamp}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(db_copy, "budget_buddy.db")
        z.write(xlsx, "budget-buddy-data.xlsx")
        z.writestr("RESTORE.txt", RESTORE_TEXT.format(when=datetime.now().strftime("%Y-%m-%d %H:%M")))
    os.remove(db_copy)
    os.remove(xlsx)
    return zip_path
