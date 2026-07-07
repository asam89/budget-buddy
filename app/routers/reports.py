"""Reports API: Category×Month pivot, Entity P&L, Entity comparison."""

from typing import Optional
from datetime import datetime, date
from calendar import monthrange
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, select

from app.database import get_db
from app.models import (
    Transaction, TransactionSplit, Category, Entity, User,
)
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _format(amount: float) -> float:
    return round(amount, 2)


def _month_range(start: date, end: date) -> list[str]:
    """Return sorted list of 'YYYY-MM' strings covering start..end."""
    months = []
    cur = start.replace(day=1)
    while cur <= end:
        months.append(cur.strftime("%Y-%m"))
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return months


def _month_end(ym: str) -> date:
    y, m = int(ym[:4]), int(ym[5:7])
    _, last_day = monthrange(y, m)
    return date(y, m, last_day)


def _month_start(ym: str) -> date:
    y, m = int(ym[:4]), int(ym[5:7])
    return date(y, m, 1)


def _get_entity_txns(
    db: Session,
    entity_id: int,
    start: date,
    end: date,
) -> list[Transaction]:
    """Get confirmed transactions for an entity (direct + split-attributed)."""
    split_txn_ids = select(TransactionSplit.transaction_id).where(
        TransactionSplit.entity_id == entity_id
    )
    return (
        db.query(Transaction)
        .filter(
            Transaction.date >= start,
            Transaction.date <= end,
            Transaction.review_status == "confirmed",
            or_(
                Transaction.entity_id == entity_id,
                Transaction.id.in_(split_txn_ids),
            ),
        )
        .all()
    )


def _effective_amount(txn: Transaction, entity_id: int) -> float:
    """For a transaction, return the amount attributable to entity_id.
    If the txn is split, return only the split portion for this entity.
    """
    if txn.splits:
        return sum(s.amount for s in txn.splits if s.entity_id == entity_id)
    return txn.amount


# ------------------------------------------------------------------
# 1. Category × Month matrix
# ------------------------------------------------------------------

@router.get("/category-month")
def category_month_matrix(
    entity_id: Optional[int] = None,
    months: int = Query(default=6, ge=1, le=24),
    mode: str = Query(default="expense"),  # expense | income | net
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Category × Month pivot. Rows = categories, columns = months."""
    now = datetime.utcnow().date()
    start = now.replace(day=1)
    for _ in range(months - 1):
        if start.month == 1:
            start = start.replace(year=start.year - 1, month=12)
        else:
            start = start.replace(month=start.month - 1)

    month_labels = _month_range(start, now)

    # Get all categories for row headers
    categories = db.query(Category).order_by(Category.name).all()
    cat_map = {c.id: c for c in categories}

    # Gather transactions
    if entity_id is not None:
        txns = _get_entity_txns(db, entity_id, start, now)
    else:
        txns = (
            db.query(Transaction)
            .filter(
                Transaction.date >= start,
                Transaction.date <= now,
                Transaction.review_status == "confirmed",
            )
            .all()
        )

    # Build matrix: category_id -> month -> amount
    matrix: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    uncat_key = 0  # sentinel for "Uncategorized"

    for txn in txns:
        ym = txn.date.strftime("%Y-%m")
        if ym not in month_labels:
            continue

        amt = _effective_amount(txn, entity_id) if entity_id else txn.amount
        cat_id = txn.category_id or uncat_key

        if mode == "expense" and amt > 0:
            matrix[cat_id][ym] += amt
        elif mode == "income" and amt < 0:
            matrix[cat_id][ym] += abs(amt)
        elif mode == "net":
            matrix[cat_id][ym] += amt

    # Build response rows
    rows = []
    for cat_id, month_totals in sorted(matrix.items(), key=lambda x: x[0]):
        cat_name = "Uncategorized" if cat_id == uncat_key else (
            cat_map[cat_id].name if cat_id in cat_map else f"#{cat_id}"
        )
        parent_name = None
        if cat_id in cat_map and cat_map[cat_id].parent_id:
            parent = cat_map.get(cat_map[cat_id].parent_id)
            if parent:
                parent_name = parent.name

        values = [_format(month_totals.get(m, 0)) for m in month_labels]
        row_total = _format(sum(values))
        row_avg = _format(row_total / len(month_labels)) if month_labels else 0

        rows.append({
            "category_id": cat_id if cat_id != uncat_key else None,
            "category": cat_name,
            "parent_category": parent_name,
            "months": dict(zip(month_labels, values)),
            "total": row_total,
            "average": row_avg,
        })

    return {
        "months": month_labels,
        "mode": mode,
        "entity_id": entity_id,
        "rows": rows,
    }


# ------------------------------------------------------------------
# 2. Entity P&L
# ------------------------------------------------------------------

@router.get("/entity-pnl")
def entity_pnl(
    entity_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Income / Expenses / Net for a single entity, grouped by category."""
    now = datetime.utcnow().date()
    if not start_date:
        start_date = now.replace(day=1)
    if not end_date:
        end_date = now

    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Entity not found")

    txns = _get_entity_txns(db, entity_id, start_date, end_date)

    cat_map = {c.id: c.name for c in db.query(Category).all()}

    income_lines: dict[str, float] = defaultdict(float)
    expense_lines: dict[str, float] = defaultdict(float)

    for txn in txns:
        amt = _effective_amount(txn, entity_id)
        cat_name = cat_map.get(txn.category_id, "Uncategorized") if txn.category_id else "Uncategorized"

        if amt < 0:
            income_lines[cat_name] += abs(amt)
        elif amt > 0:
            expense_lines[cat_name] += amt

    total_income = _format(sum(income_lines.values()))
    total_expenses = _format(sum(expense_lines.values()))
    net = _format(total_income - total_expenses)

    return {
        "entity_id": entity_id,
        "entity_name": entity.name,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "income": [
            {"category": k, "amount": _format(v)}
            for k, v in sorted(income_lines.items())
        ],
        "expenses": [
            {"category": k, "amount": _format(v)}
            for k, v in sorted(expense_lines.items())
        ],
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net": net,
    }


# ------------------------------------------------------------------
# 3. Entity comparison
# ------------------------------------------------------------------

@router.get("/entity-comparison")
def entity_comparison(
    months: int = Query(default=6, ge=1, le=24),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Side-by-side monthly net for all active entities."""
    now = datetime.utcnow().date()
    start = now.replace(day=1)
    for _ in range(months - 1):
        if start.month == 1:
            start = start.replace(year=start.year - 1, month=12)
        else:
            start = start.replace(month=start.month - 1)

    month_labels = _month_range(start, now)
    entities = db.query(Entity).filter(Entity.is_active == True).all()

    result = []
    for entity in entities:
        txns = _get_entity_txns(db, entity.id, start, now)

        monthly: dict[str, dict[str, float]] = {}
        for m in month_labels:
            monthly[m] = {"income": 0.0, "expenses": 0.0, "net": 0.0}

        for txn in txns:
            ym = txn.date.strftime("%Y-%m")
            if ym not in monthly:
                continue
            amt = _effective_amount(txn, entity.id)
            if amt < 0:
                monthly[ym]["income"] += abs(amt)
            elif amt > 0:
                monthly[ym]["expenses"] += amt

        for m in month_labels:
            monthly[m]["net"] = _format(monthly[m]["income"] - monthly[m]["expenses"])
            monthly[m]["income"] = _format(monthly[m]["income"])
            monthly[m]["expenses"] = _format(monthly[m]["expenses"])

        result.append({
            "entity_id": entity.id,
            "entity_name": entity.name,
            "months": monthly,
        })

    return {
        "month_labels": month_labels,
        "entities": result,
    }
