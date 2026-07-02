from typing import Optional

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Transaction, User
from app.schemas import TransactionOut, TransactionCreate, TransactionReview
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("/", response_model=list[TransactionOut])
def list_transactions(
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    review_status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Transaction)

    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if review_status:
        query = query.filter(Transaction.review_status == review_status)
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)

    return (
        query.order_by(Transaction.date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/pending-review", response_model=list[TransactionOut])
def list_pending_review(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return (
        db.query(Transaction)
        .filter(Transaction.review_status == "pending")
        .order_by(Transaction.date.desc())
        .all()
    )


@router.post("/", response_model=TransactionOut, status_code=201)
def create_transaction(
    data: TransactionCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    dedup = Transaction.compute_dedup_hash(data.date, data.amount, data.name, data.account_id)
    existing = db.query(Transaction).filter(Transaction.dedup_hash == dedup).first()
    if existing:
        raise HTTPException(status_code=409, detail="Duplicate transaction detected")

    txn = Transaction(
        account_id=data.account_id,
        amount=data.amount,
        date=data.date,
        name=data.name,
        merchant_name=data.merchant_name,
        category_id=data.category_id,
        notes=data.notes,
        review_status="confirmed",
        review_source="manual",
        dedup_hash=dedup,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@router.put("/{transaction_id}/review", response_model=TransactionOut)
def review_transaction(
    transaction_id: int,
    data: TransactionReview,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    txn.review_status = data.review_status
    if data.name is not None:
        txn.name = data.name
    if data.amount is not None:
        txn.amount = data.amount
    if data.date is not None:
        txn.date = data.date
    if data.category_id is not None:
        txn.category_id = data.category_id
    if data.merchant_name is not None:
        txn.merchant_name = data.merchant_name

    if data.review_status == "confirmed":
        txn.dedup_hash = Transaction.compute_dedup_hash(
            txn.date, txn.amount, txn.name, txn.account_id
        )

    db.commit()
    db.refresh(txn)
    return txn


@router.get("/{transaction_id}", response_model=TransactionOut)
def get_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


@router.delete("/{transaction_id}", status_code=204)
def delete_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(txn)
    db.commit()
