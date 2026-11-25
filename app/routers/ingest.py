"""Inbox for outside tools (Muse, iPhone Shortcuts): send spending with an API token.

Authenticate with ``Authorization: Bearer bb_...`` (create tokens in Settings).
Everything sent here waits on the Review page until someone approves it.
"""

import base64
import binascii
from datetime import date as DateType
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApiToken
from app.services.spending import (
    SpendingError, check_api_token, find_category, find_entity, record_spending, store_receipt,
)

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


def require_api_token(authorization: Optional[str] = Header(default=None),
                      db: Session = Depends(get_db)) -> ApiToken:
    raw = (authorization or "").removeprefix("Bearer ").strip()
    token = check_api_token(db, raw)
    if token is None:
        raise HTTPException(status_code=401, detail="Missing or invalid API token",
                            headers={"WWW-Authenticate": "Bearer"})
    return token


class IngestSpending(BaseModel):
    amount: float
    merchant: Optional[str] = None
    description: Optional[str] = None
    date: Optional[DateType] = None
    category: Optional[str] = None     # matched to an existing expense line by name
    business: Optional[str] = None     # matched to an entity by name; default if omitted
    notes: Optional[str] = None
    external_id: Optional[str] = None  # your own ID; resending it never duplicates
    receipt_base64: Optional[str] = None
    receipt_filename: Optional[str] = None
    receipt_content_type: Optional[str] = None


@router.post("/spending")
def ingest_spending(data: IngestSpending, db: Session = Depends(get_db),
                    token: ApiToken = Depends(require_api_token)):
    notes = data.notes
    cat = find_category(db, data.category)
    if data.category and cat is None:
        notes = ((notes + "\n") if notes else "") + f"Suggested category: {data.category}"
    ent = find_entity(db, data.business)
    if data.business and ent is None:
        notes = ((notes + "\n") if notes else "") + f"Suggested business: {data.business}"
    try:
        receipt_id = None
        if data.receipt_base64:
            try:
                raw = base64.b64decode(data.receipt_base64, validate=True)
            except (binascii.Error, ValueError):
                raise SpendingError("receipt_base64 isn't valid base64")
            receipt_id = store_receipt(db, raw, data.receipt_filename, data.receipt_content_type).id
        txn, created = record_spending(
            db, amount=data.amount, description=data.description or data.merchant or "",
            merchant=data.merchant, on_date=data.date, category_id=cat.id if cat else None,
            entity_id=ent.id if ent else None, notes=(notes or "") + f"\nSent by: {token.name}",
            receipt_id=receipt_id, source="api", pending=True, external_id=data.external_id,
        )
    except SpendingError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    reason = None
    if not created:
        reason = ("external_id already received" if data.external_id and txn.dedup_hash and txn.dedup_hash.startswith("ext:")
                  else "this receipt was already recorded")
    return {"id": txn.id, "status": txn.review_status, "duplicate": not created, "duplicate_reason": reason,
            "category_matched": cat.name if cat else None, "business_matched": ent.name if ent else None}
