from typing import Optional

import hashlib
import io
import logging
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.models import Transaction, ImportSource, Account

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"date", "amount", "name"}


def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def import_csv(
    db: Session,
    content: bytes,
    filename: str,
    account_id: int,
    has_header: bool = True,
) -> ImportSource:
    return _import_tabular(db, content, filename, account_id, "csv", has_header)


def import_excel(
    db: Session,
    content: bytes,
    filename: str,
    account_id: int,
) -> ImportSource:
    return _import_tabular(db, content, filename, account_id, "excel", True)


def _import_tabular(
    db: Session,
    content: bytes,
    filename: str,
    account_id: int,
    source_type: str,
    has_header: bool,
) -> ImportSource:
    fhash = file_hash(content)

    existing = db.query(ImportSource).filter(ImportSource.file_hash == fhash).first()
    if existing:
        return ImportSource(
            source_type=source_type,
            filename=filename,
            file_hash=fhash,
            record_count=0,
            status="duplicate",
            error_message="This file has already been imported",
        )

    source = ImportSource(
        source_type=source_type,
        filename=filename,
        file_hash=fhash,
        status="processing",
    )
    db.add(source)
    db.flush()

    try:
        if source_type == "csv":
            df = pd.read_csv(
                io.BytesIO(content),
                header=0 if has_header else None,
            )
        else:
            df = pd.read_excel(io.BytesIO(content))

        df.columns = [c.strip().lower() for c in df.columns]

        col_map = _detect_columns(df.columns.tolist())
        if not col_map:
            source.status = "failed"
            source.error_message = (
                f"Could not detect required columns. Found: {list(df.columns)}. "
                f"Need at least: {REQUIRED_COLUMNS}"
            )
            db.commit()
            return source

        added = 0
        for _, row in df.iterrows():
            try:
                txn_date = _parse_date(row[col_map["date"]])
                amount = float(row[col_map["amount"]])
                name = str(row[col_map["name"]]).strip()
            except (ValueError, TypeError):
                continue

            merchant = str(row[col_map["merchant"]]).strip() if col_map.get("merchant") else None
            category_name = str(row[col_map["category"]]).strip() if col_map.get("category") else None

            dedup = Transaction.compute_dedup_hash(txn_date, amount, name, account_id)
            if db.query(Transaction).filter(Transaction.dedup_hash == dedup).first():
                continue

            txn = Transaction(
                account_id=account_id,
                import_source_id=source.id,
                amount=amount,
                date=txn_date,
                name=name,
                merchant_name=merchant if merchant and merchant != "nan" else None,
                review_status="confirmed",
                review_source="csv_import" if source_type == "csv" else "excel_import",
                dedup_hash=dedup,
                source_file=filename,
            )
            db.add(txn)
            added += 1

        source.record_count = added
        source.status = "completed"
        db.commit()

    except Exception as e:
        logger.exception("Import failed")
        source.status = "failed"
        source.error_message = str(e)
        db.commit()

    return source


def _detect_columns(columns: list[str]) -> Optional[dict[str, str]]:
    mapping: dict[str, str] = {}

    date_candidates = ["date", "transaction_date", "trans_date", "posting_date", "txn_date"]
    amount_candidates = ["amount", "transaction_amount", "debit", "value", "total"]
    name_candidates = ["name", "description", "merchant", "payee", "memo", "transaction_description"]
    merchant_candidates = ["merchant", "merchant_name", "vendor"]
    category_candidates = ["category", "type", "transaction_type"]

    for candidates, key in [
        (date_candidates, "date"),
        (amount_candidates, "amount"),
        (name_candidates, "name"),
    ]:
        for c in candidates:
            if c in columns:
                mapping[key] = c
                break

    if not all(k in mapping for k in REQUIRED_COLUMNS):
        return None

    for candidates, key in [
        (merchant_candidates, "merchant"),
        (category_candidates, "category"),
    ]:
        for c in candidates:
            if c in columns and c != mapping.get("name"):
                mapping[key] = c
                break

    return mapping


def _parse_date(val) -> date:
    if isinstance(val, (datetime, date)):
        return val if isinstance(val, date) else val.date()
    if isinstance(val, pd.Timestamp):
        return val.date()
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return pd.to_datetime(s).date()
