from typing import Optional

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from sqlalchemy import func, or_, select

from app.database import get_db
from app.models import Transaction, TransactionSplit, Entity, User, Category
from app.schemas import (
    TransactionOut, TransactionCreate, TransactionReview,
    TransactionSplitsRequest, TransactionSplitOut,
    TransactionBulkEntityAssign, TransactionInlineEdit,
)
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("/", response_model=list[TransactionOut])
def list_transactions(
    response: Response,
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    entity_id: Optional[int] = None,
    txn_type: Optional[str] = None,
    review_status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    q: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    sort_by: str = Query(default="date"),
    sort_dir: str = Query(default="desc"),
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
    if entity_id is not None:
        split_txn_ids = select(TransactionSplit.transaction_id).where(
            TransactionSplit.entity_id == entity_id
        )
        query = query.filter(
            or_(Transaction.entity_id == entity_id, Transaction.id.in_(split_txn_ids))
        )
    if txn_type:
        query = query.filter(Transaction.txn_type == txn_type)
    if review_status:
        query = query.filter(Transaction.review_status == review_status)
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(Transaction.name.ilike(pattern), Transaction.merchant_name.ilike(pattern))
        )
    if min_amount is not None:
        query = query.filter(Transaction.amount >= min_amount)
    if max_amount is not None:
        query = query.filter(Transaction.amount <= max_amount)

    # Total count header for pagination
    total = query.count()
    response.headers["X-Total-Count"] = str(total)

    # Sorting
    sort_col = getattr(Transaction, sort_by, Transaction.date)
    order = sort_col.desc() if sort_dir == "desc" else sort_col.asc()

    return (
        query.order_by(order)
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


@router.get("/needs-category", response_model=list[TransactionOut])
def list_needs_category(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Confirmed transactions with no category — the single home for anything
    uncategorized. There is no catch-all category; these wait here for the
    user to assign a real one."""
    return (
        db.query(Transaction)
        .filter(
            Transaction.review_status == "confirmed",
            Transaction.category_id.is_(None),
        )
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

    # Determine entity: explicit, or fall back to default
    entity_id = data.entity_id
    entity_source = "manual" if entity_id else "default"
    if not entity_id:
        default_entity = db.query(Entity).filter(Entity.is_default == True).first()
        if default_entity:
            entity_id = default_entity.id

    # Infer txn_type from amount sign: negative = income, positive = expense
    txn_type = "income" if data.amount < 0 else "expense"

    txn = Transaction(
        account_id=data.account_id,
        amount=data.amount,
        date=data.date,
        name=data.name,
        merchant_name=data.merchant_name,
        category_id=data.category_id,
        entity_id=entity_id,
        entity_source=entity_source,
        txn_type=txn_type,
        notes=data.notes,
        review_status="confirmed",
        review_source="manual",
        dedup_hash=dedup,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@router.get("/totals")
def get_transaction_totals(
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    entity_id: Optional[int] = None,
    txn_type: Optional[str] = None,
    review_status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    q: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Server-computed totals for the current filter set (all pages, not just visible)."""
    query = db.query(Transaction).filter(Transaction.review_status == "confirmed")

    if account_id:
        query = query.filter(Transaction.account_id == account_id)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if entity_id is not None:
        split_txn_ids = select(TransactionSplit.transaction_id).where(
            TransactionSplit.entity_id == entity_id
        )
        query = query.filter(
            or_(Transaction.entity_id == entity_id, Transaction.id.in_(split_txn_ids))
        )
    if txn_type:
        query = query.filter(Transaction.txn_type == txn_type)
    if review_status:
        query = query.filter(Transaction.review_status == review_status)
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            or_(Transaction.name.ilike(pattern), Transaction.merchant_name.ilike(pattern))
        )
    if min_amount is not None:
        query = query.filter(Transaction.amount >= min_amount)
    if max_amount is not None:
        query = query.filter(Transaction.amount <= max_amount)

    txns = query.all()
    count = len(txns)
    total_sum = round(sum(t.amount for t in txns), 2)
    income = round(sum(t.amount for t in txns if t.amount < 0), 2)
    expenses = round(sum(t.amount for t in txns if t.amount > 0), 2)

    entity_subtotals: dict[int, float] = {}
    for t in txns:
        if t.entity_id:
            entity_subtotals[t.entity_id] = round(
                entity_subtotals.get(t.entity_id, 0) + t.amount, 2
            )
        for s in t.splits:
            entity_subtotals[s.entity_id] = round(
                entity_subtotals.get(s.entity_id, 0) + s.amount, 2
            )

    return {
        "count": count,
        "sum": total_sum,
        "income": income,
        "expenses": expenses,
        "entity_subtotals": entity_subtotals,
    }


@router.post("/bulk-entity", response_model=dict)
def bulk_assign_entity(
    data: TransactionBulkEntityAssign,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    entity = db.query(Entity).filter(Entity.id == data.entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    updated = 0
    for txn_id in data.transaction_ids:
        txn = db.query(Transaction).filter(Transaction.id == txn_id).first()
        if txn and not txn.splits:
            txn.entity_id = data.entity_id
            txn.entity_source = "manual"
            updated += 1

    db.commit()
    return {"updated_count": updated}


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


@router.patch("/{transaction_id}", response_model=TransactionOut)
def inline_edit_transaction(
    transaction_id: int,
    data: TransactionInlineEdit,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Inline edit: category, entity, notes, name always editable.
    Amount/date only for manual transactions (to protect dedup hashes)."""
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    is_manual = txn.review_source == "manual"

    if data.name is not None:
        txn.name = data.name
    if data.category_id is not None:
        txn.category_id = data.category_id
    if data.entity_id is not None:
        if txn.splits:
            raise HTTPException(
                status_code=422,
                detail="Transaction has splits — remove splits first.",
            )
        entity = db.query(Entity).filter(Entity.id == data.entity_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        txn.entity_id = data.entity_id
        txn.entity_source = "manual"
    if data.notes is not None:
        txn.notes = data.notes
    if data.amount is not None:
        if not is_manual:
            raise HTTPException(
                status_code=422,
                detail="Amount can only be edited on manually-created transactions.",
            )
        txn.amount = data.amount
        txn.txn_type = "income" if data.amount < 0 else "expense"
    if data.date is not None:
        if not is_manual:
            raise HTTPException(
                status_code=422,
                detail="Date can only be edited on manually-created transactions.",
            )
        txn.date = data.date

    if is_manual and (data.amount is not None or data.date is not None or data.name is not None):
        txn.dedup_hash = Transaction.compute_dedup_hash(
            txn.date, txn.amount, txn.name, txn.account_id
        )

    db.commit()
    db.refresh(txn)
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


@router.patch("/{transaction_id}/entity")
def set_transaction_entity(
    transaction_id: int,
    entity_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    if txn.splits:
        raise HTTPException(
            status_code=422,
            detail="Transaction has splits — cannot set a single entity. Remove splits first.",
        )
    txn.entity_id = entity_id
    txn.entity_source = "manual"
    db.commit()
    db.refresh(txn)
    return TransactionOut.model_validate(txn)


@router.put("/{transaction_id}/splits", response_model=list[TransactionSplitOut])
def set_transaction_splits(
    transaction_id: int,
    data: TransactionSplitsRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if len(data.splits) < 2:
        raise HTTPException(status_code=422, detail="Splits require at least 2 entries")

    # Validate split amounts sum to transaction amount
    split_total = round(sum(s.amount for s in data.splits), 2)
    if split_total != round(txn.amount, 2):
        raise HTTPException(
            status_code=422,
            detail=f"Split amounts ({split_total}) must sum to transaction amount ({round(txn.amount, 2)})",
        )

    # Validate all entities exist
    for s in data.splits:
        if not db.query(Entity).filter(Entity.id == s.entity_id).first():
            raise HTTPException(status_code=404, detail=f"Entity {s.entity_id} not found")

    # Clear existing splits and entity_id
    db.query(TransactionSplit).filter(TransactionSplit.transaction_id == transaction_id).delete()
    txn.entity_id = None
    txn.entity_source = "manual"

    splits = []
    for s in data.splits:
        split = TransactionSplit(
            transaction_id=transaction_id,
            entity_id=s.entity_id,
            amount=s.amount,
            percent=s.percent,
            notes=s.notes,
        )
        db.add(split)
        splits.append(split)

    db.commit()
    for sp in splits:
        db.refresh(sp)
    return splits


@router.delete("/{transaction_id}/splits", status_code=204)
def delete_transaction_splits(
    transaction_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.query(TransactionSplit).filter(TransactionSplit.transaction_id == transaction_id).delete()
    # Reassign to default entity
    default_entity = db.query(Entity).filter(Entity.is_default == True).first()
    if default_entity:
        txn.entity_id = default_entity.id
        txn.entity_source = "default"
    db.commit()

