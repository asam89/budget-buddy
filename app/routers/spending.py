"""Everyday spending: quick add, receipt scan, receipt viewing, API tokens."""

from dataclasses import asdict
from datetime import date, datetime
from datetime import date as DateType
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApiToken, Category, Entity, Receipt, User
from app.services.ai_parser import _get_llm_provider
from app.services.spending import (
    MAX_RECEIPT_BYTES, SpendingError, create_api_token, manual_actual_overrides,
    record_spending, scan_receipt, store_receipt,
)
from app.utils.auth import get_current_user, require_admin

router = APIRouter(prefix="/api/spending", tags=["spending"])


def _txn_out(txn, db: Session) -> dict:
    return {
        "id": txn.id, "date": txn.date.isoformat(), "amount": txn.amount, "name": txn.name,
        "merchant_name": txn.merchant_name, "category_id": txn.category_id, "entity_id": txn.entity_id,
        "review_status": txn.review_status, "receipt_id": txn.receipt_id,
        "manual_actual_overrides": manual_actual_overrides(db, txn),
    }


@router.get("/options")
def spending_options(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    cats = db.query(Category).filter(Category.kind == "expense").order_by(Category.name).all()
    ents = db.query(Entity).filter(Entity.is_active == True).order_by(Entity.name).all()  # noqa: E712
    default = next((e.id for e in ents if e.is_default), None)
    return {
        "categories": [{"id": c.id, "name": c.name, "entity_id": c.entity_id} for c in cats],
        "entities": [{"id": e.id, "name": e.name} for e in ents],
        "default_entity_id": default,
        "today": date.today().isoformat(),
    }


class SpendingCreate(BaseModel):
    amount: float
    description: str
    date: Optional[DateType] = None
    merchant: Optional[str] = None
    category_id: Optional[int] = None
    new_category: Optional[str] = None
    entity_id: Optional[int] = None
    notes: Optional[str] = None
    receipt_id: Optional[int] = None


@router.post("", status_code=201)
def add_spending(data: SpendingCreate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    """Quick add (or save a scanned receipt). Saved as confirmed: you checked it."""
    try:
        txn, created = record_spending(
            db, amount=data.amount, description=data.description, on_date=data.date,
            merchant=data.merchant, category_id=data.category_id, new_category=data.new_category,
            entity_id=data.entity_id, notes=data.notes, receipt_id=data.receipt_id,
            source="receipt" if data.receipt_id else "quick_add",
        )
    except SpendingError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {**_txn_out(txn, db), "created": created}


@router.post("/receipt/scan")
async def scan(file: UploadFile = File(...), db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    """Store a receipt and read its details. Nothing is recorded until you save."""
    data = await file.read(MAX_RECEIPT_BYTES + 1)
    try:
        receipt = store_receipt(db, data, file.filename, file.content_type)
        db.commit()
    except SpendingError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return asdict(scan_receipt(db, receipt, _get_llm_provider(db)))


@router.get("/receipts/{receipt_id}")
def get_receipt(receipt_id: int, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    r = db.get(Receipt, receipt_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    name = (r.filename or f"receipt-{r.id}").replace('"', "")
    return Response(r.data, media_type=r.content_type,
                    headers={"Content-Disposition": f'inline; filename="{name}"',
                             "Cache-Control": "private, max-age=3600",
                             "X-Content-Type-Options": "nosniff"})


# ---- API tokens (admins) ----

def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


@router.get("/tokens")
def list_tokens(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    rows = db.query(ApiToken).order_by(ApiToken.created_at.desc()).all()
    return [{"id": t.id, "name": t.name, "prefix": t.prefix, "created_at": _iso(t.created_at),
             "last_used_at": _iso(t.last_used_at), "revoked": t.revoked_at is not None} for t in rows]


class TokenCreate(BaseModel):
    name: str


@router.post("/tokens", status_code=201)
def new_token(data: TokenCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    try:
        raw, row = create_api_token(db, data.name, admin.id)
    except SpendingError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"id": row.id, "name": row.name, "token": raw}


@router.delete("/tokens/{token_id}", status_code=204)
def revoke_token(token_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    row = db.get(ApiToken, token_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Token not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.utcnow()
        db.commit()
