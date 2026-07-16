"""Manual actuals API: per-line, per-month values entered directly (Excel-style).

Reconciliation and totals come from ``app.services.aggregation`` so this router
never computes an actual on its own.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Category, ManualActual, User
from app.schemas import ManualActualBulk, ManualActualUpsert
from app.services.aggregation import (
    effective_actual,
    is_valid_year_month,
    month_totals,
    year_grid,
    year_summary,
)
from app.services.entity_seed import resolve_entity_id
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/actuals", tags=["actuals"])


def _validate_ym(year_month: str) -> None:
    if not is_valid_year_month(year_month):
        raise HTTPException(status_code=422, detail="year_month must be 'YYYY-MM'")


def _require_category(db: Session, category_id: int) -> Category:
    cat = db.query(Category).filter(Category.id == category_id).first()
    if cat is None:
        raise HTTPException(status_code=404, detail=f"Category {category_id} not found")
    return cat


@router.get("/")
def get_actuals_year(
    year: int,
    entity_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Full grid for a year: every category x 12 months with source per cell.

    Batched in ``year_grid`` (a handful of queries) rather than a per-cell
    round trip, so a large category set doesn't fan out into hundreds of
    encrypted-SQLite queries per page load. Optionally scoped to one entity.
    """
    return {"year": year, "entity_id": entity_id, "lines": year_grid(db, year, entity_id)}


@router.post("/")
def upsert_actual(
    data: ManualActualUpsert,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Create or update the manual actual for one (category, month, entity)."""
    _validate_ym(data.year_month)
    _require_category(db, data.category_id)
    entity_id = resolve_entity_id(db, data.entity_id)

    existing = (
        db.query(ManualActual)
        .filter(
            ManualActual.category_id == data.category_id,
            ManualActual.year_month == data.year_month,
            ManualActual.entity_id == entity_id,
        )
        .first()
    )
    if existing is not None:
        existing.amount = data.amount
        existing.note = data.note
        existing.updated_at = datetime.utcnow()
    else:
        db.add(ManualActual(
            category_id=data.category_id,
            year_month=data.year_month,
            amount=data.amount,
            note=data.note,
            entity_id=entity_id,
        ))
    db.commit()

    cat = _require_category(db, data.category_id)
    eff = effective_actual(db, cat, data.year_month, entity_id)
    return {
        "category_id": cat.id,
        "year_month": data.year_month,
        "entity_id": entity_id,
        "effective": eff.amount,
        "source": eff.source,
        "transaction_sum": eff.transaction_sum,
        "manual_amount": eff.manual_amount,
    }


@router.post("/bulk")
def bulk_upsert(
    data: ManualActualBulk,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Atomically upsert many (category, month) manual actuals (grid paste)."""
    for entry in data.entries:
        _validate_ym(entry.year_month)
        _require_category(db, entry.category_id)

    entity_id = resolve_entity_id(db, data.entity_id)
    for entry in data.entries:
        existing = (
            db.query(ManualActual)
            .filter(
                ManualActual.category_id == entry.category_id,
                ManualActual.year_month == entry.year_month,
                ManualActual.entity_id == entity_id,
            )
            .first()
        )
        if existing is not None:
            existing.amount = entry.amount
            existing.updated_at = datetime.utcnow()
        else:
            db.add(ManualActual(
                category_id=entry.category_id,
                year_month=entry.year_month,
                amount=entry.amount,
                entity_id=entity_id,
            ))
    db.commit()
    return {"upserted": len(data.entries)}


@router.delete("/{category_id}/{year_month}", status_code=204)
def delete_actual(
    category_id: int,
    year_month: str,
    entity_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Delete a manual actual, reverting the cell to transaction-derived."""
    _validate_ym(year_month)
    entity_id = resolve_entity_id(db, entity_id)
    existing = (
        db.query(ManualActual)
        .filter(
            ManualActual.category_id == category_id,
            ManualActual.year_month == year_month,
            ManualActual.entity_id == entity_id,
        )
        .first()
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="No manual actual for that line-month")
    db.delete(existing)
    db.commit()


@router.get("/month-totals")
def get_month_totals(
    year_month: str,
    entity_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    _validate_ym(year_month)
    return month_totals(db, year_month, entity_id).__dict__


@router.get("/year-summary")
def get_year_summary(
    year: int,
    entity_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    summary = year_summary(db, year, entity_id=entity_id)
    return {
        "year": summary.year,
        "months": [m.__dict__ for m in summary.months],
        "saved_budget_year": summary.saved_budget_year,
        "income_budget_year": summary.income_budget_year,
        "expense_budget_year": summary.expense_budget_year,
        "saved_actual_ytd": summary.saved_actual_ytd,
        "income_actual_ytd": summary.income_actual_ytd,
        "expense_actual_ytd": summary.expense_actual_ytd,
        "ytd_through_month": summary.ytd_through_month,
    }
