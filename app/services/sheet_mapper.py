"""Smart spreadsheet import: detect headers, profile columns, propose mapping."""

import hashlib
import io
import json
import logging
import re
from datetime import datetime, date
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.models import (
    Account, Category, Entity, ImportSource, ImportTemplate, Transaction,
)
from app.services.rule_engine import apply_rules_to_transaction, infer_txn_type

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Header signature for template matching
# ------------------------------------------------------------------

def header_signature(columns: list[str]) -> str:
    normalized = sorted(c.strip().lower() for c in columns if c.strip())
    return hashlib.sha256("|".join(normalized).encode()).hexdigest()[:32]


# ------------------------------------------------------------------
# Deterministic pre-pass: find header row, clean data
# ------------------------------------------------------------------

_TOTAL_RE = re.compile(r"^(total|subtotal|sum|grand total)s?\b", re.IGNORECASE)


def detect_header_row(df_raw: pd.DataFrame, max_scan: int = 10) -> int:
    """Find the header row by looking for the row with the most non-null string values."""
    best_row, best_score = 0, 0
    nrows = min(len(df_raw), max_scan)
    for i in range(nrows):
        row = df_raw.iloc[i]
        score = sum(
            1 for v in row
            if isinstance(v, str) and v.strip() and not v.strip().replace(".", "").isdigit()
        )
        if score > best_score:
            best_score = score
            best_row = i
    return best_row


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Drop empty rows/cols, remove total/summary rows."""
    df = df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)

    # Remove total/summary rows
    mask = pd.Series(True, index=df.index)
    for col in df.columns:
        if df[col].dtype == object:
            mask = mask & ~df[col].astype(str).str.match(_TOTAL_RE, na=False)
    df = df[mask].reset_index(drop=True)

    return df


def profile_columns(df: pd.DataFrame) -> list[dict]:
    """Profile each column for type detection."""
    profiles = []
    for col in df.columns:
        series = df[col].dropna()
        n = len(series)
        if n == 0:
            profiles.append({"column": col, "dtype": "empty", "samples": []})
            continue

        # Date parse rate
        date_ok = 0
        for v in series.head(20):
            try:
                pd.to_datetime(v)
                date_ok += 1
            except (ValueError, TypeError):
                pass
        date_rate = date_ok / min(n, 20) if n > 0 else 0

        # Numeric rate
        num_ok = 0
        for v in series.head(20):
            try:
                float(str(v).replace(",", "").replace("$", "").replace("-", ""))
                num_ok += 1
            except (ValueError, TypeError):
                pass
        num_rate = num_ok / min(n, 20) if n > 0 else 0

        samples = [str(v) for v in series.head(5)]
        profiles.append({
            "column": col,
            "dtype": str(series.dtype),
            "count": n,
            "date_parse_rate": round(date_rate, 2),
            "numeric_rate": round(num_rate, 2),
            "samples": samples,
        })
    return profiles


# ------------------------------------------------------------------
# Heuristic mapping (no AI)
# ------------------------------------------------------------------

def heuristic_mapping(profiles: list[dict]) -> dict:
    """Best-effort column mapping without AI."""
    mapping = {}
    used = set()

    # Date: highest date parse rate
    date_candidates = sorted(
        [p for p in profiles if p["date_parse_rate"] > 0.5],
        key=lambda p: -p["date_parse_rate"],
    )
    if date_candidates:
        mapping["date"] = date_candidates[0]["column"]
        used.add(date_candidates[0]["column"])

    # Amount: highest numeric rate (excluding date)
    amount_candidates = sorted(
        [p for p in profiles if p["column"] not in used and p["numeric_rate"] > 0.5],
        key=lambda p: -p["numeric_rate"],
    )
    if amount_candidates:
        mapping["amount"] = amount_candidates[0]["column"]
        used.add(amount_candidates[0]["column"])

    # Debit/credit: check for separate columns
    for p in profiles:
        col_lower = p["column"].lower()
        if "debit" in col_lower and p["column"] not in used:
            mapping["debit"] = p["column"]
            used.add(p["column"])
        elif "credit" in col_lower and p["column"] not in used:
            mapping["credit"] = p["column"]
            used.add(p["column"])

    # If we found debit+credit but no amount, merge them
    if "debit" in mapping and "credit" in mapping and "amount" not in mapping:
        mapping["amount_mode"] = "debit_credit"

    # Name/description: longest average string length of remaining text columns
    text_cols = [
        p for p in profiles
        if p["column"] not in used and p["numeric_rate"] < 0.3 and p["date_parse_rate"] < 0.3
    ]
    if text_cols:
        best_name = max(text_cols, key=lambda p: sum(len(s) for s in p["samples"]) / max(len(p["samples"]), 1))
        mapping["name"] = best_name["column"]
        used.add(best_name["column"])

    # Entity: check for columns named entity, property, ledger
    for p in profiles:
        col_lower = p["column"].lower()
        if col_lower in ("entity", "property", "ledger", "house/airbnb") and p["column"] not in used:
            mapping["entity"] = p["column"]
            used.add(p["column"])
            break

    # Category: check for columns named category, type
    for p in profiles:
        col_lower = p["column"].lower()
        if col_lower in ("category", "type", "expense type") and p["column"] not in used:
            mapping["category"] = p["column"]
            used.add(p["column"])
            break

    # Notes: any remaining text column
    remaining_text = [
        p for p in profiles
        if p["column"] not in used and p["numeric_rate"] < 0.3 and p["date_parse_rate"] < 0.3
    ]
    if remaining_text:
        mapping["notes"] = remaining_text[0]["column"]

    mapping["confidence"] = "low"
    mapping["sign_convention"] = "standard"  # negative=income, positive=expense
    return mapping


# ------------------------------------------------------------------
# Parse data using a confirmed mapping
# ------------------------------------------------------------------

def parse_with_mapping(
    df: pd.DataFrame,
    mapping: dict,
    account_id: int,
    default_entity_id: Optional[int] = None,
) -> list[dict]:
    """Parse DataFrame rows using the confirmed mapping. Returns list of row dicts ready for import."""
    rows = []
    sign_flip = mapping.get("sign_convention") == "expenses_positive"
    amount_mode = mapping.get("amount_mode", "single")

    for _, row in df.iterrows():
        try:
            # Date
            date_col = mapping.get("date")
            if not date_col or pd.isna(row.get(date_col)):
                continue
            txn_date = _parse_date(row[date_col])
            if not txn_date:
                continue

            # Amount
            if amount_mode == "debit_credit":
                debit_col = mapping.get("debit", "")
                credit_col = mapping.get("credit", "")
                debit = _safe_float(row.get(debit_col, 0))
                credit = _safe_float(row.get(credit_col, 0))
                amount = debit - credit if debit else -credit
            else:
                amount_col = mapping.get("amount")
                if not amount_col:
                    continue
                amount = _safe_float(row.get(amount_col))
                if amount is None:
                    continue

            if sign_flip:
                amount = -amount

            # Name
            name_col = mapping.get("name")
            name = str(row.get(name_col, "")).strip() if name_col else ""
            if not name or name == "nan":
                name = "Unnamed"

            # Optional fields
            entity_name = None
            if mapping.get("entity"):
                val = row.get(mapping["entity"])
                if pd.notna(val):
                    entity_name = str(val).strip()

            category_name = None
            if mapping.get("category"):
                val = row.get(mapping["category"])
                if pd.notna(val):
                    category_name = str(val).strip()

            notes = None
            if mapping.get("notes"):
                val = row.get(mapping["notes"])
                if pd.notna(val):
                    notes = str(val).strip()
                    if notes == "nan":
                        notes = None

            rows.append({
                "date": txn_date,
                "amount": round(amount, 2),
                "name": name,
                "entity_name": entity_name,
                "category_name": category_name,
                "notes": notes,
                "account_id": account_id,
                "default_entity_id": default_entity_id,
            })

        except Exception:
            logger.debug("Skipping row due to parse error", exc_info=True)
            continue

    return rows


def _safe_float(val) -> Optional[float]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(str(val).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return None


def _parse_date(val) -> Optional[date]:
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
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return None


# ------------------------------------------------------------------
# Commit parsed rows to database
# ------------------------------------------------------------------

def commit_rows(
    db: Session,
    rows: list[dict],
    source: ImportSource,
    entity_map: Optional[dict[str, int]] = None,
    category_map: Optional[dict[str, int]] = None,
) -> dict:
    """Write parsed rows to the database. Returns stats."""
    added = 0
    skipped_dedup = 0
    entity_map = entity_map or {}
    category_map = category_map or {}

    for row_data in rows:
        txn_date = row_data["date"]
        amount = row_data["amount"]
        name = row_data["name"]
        account_id = row_data["account_id"]

        dedup = Transaction.compute_dedup_hash(txn_date, amount, name, account_id)
        if db.query(Transaction).filter(Transaction.dedup_hash == dedup).first():
            skipped_dedup += 1
            continue

        # Resolve entity
        entity_id = row_data.get("default_entity_id")
        entity_source = "default"
        if row_data.get("entity_name"):
            resolved = entity_map.get(row_data["entity_name"].lower())
            if resolved:
                entity_id = resolved
                entity_source = "sheet"

        # Resolve category
        category_id = None
        if row_data.get("category_name"):
            category_id = category_map.get(row_data["category_name"].lower())

        txn = Transaction(
            account_id=account_id,
            import_source_id=source.id,
            amount=amount,
            date=txn_date,
            name=name,
            entity_id=entity_id,
            entity_source=entity_source,
            category_id=category_id,
            txn_type=infer_txn_type(amount),
            notes=row_data.get("notes"),
            review_status="pending",
            review_source="sheet_import",
            dedup_hash=dedup,
        )
        db.add(txn)
        db.flush()

        # Apply entity rules (only if no entity was set from the sheet)
        if not row_data.get("entity_name"):
            apply_rules_to_transaction(db, txn)

        added += 1

    db.commit()
    source.record_count = added
    source.status = "completed"
    db.commit()

    return {"added": added, "skipped_dedup": skipped_dedup, "total": len(rows)}
