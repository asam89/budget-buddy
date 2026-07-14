"""Manual actuals API: per-line, per-month values entered directly (Excel-style).

Reconciliation and totals come from ``app.services.aggregation`` so this router
never computes an actual on its own.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Category, ManualActual, User
from app.schemas import ManualActualBulk, ManualActualUpsert
from app.services.aggregation import (
    budget_for,
    effective_actual,
    is_valid_year_month,
    month_totals,
    year_summary,
)
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
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Full grid for a year: every category x 12 months with source per cell."""
    categories = db.query(Category).order_by(Category.name).all()
    lines = []
    for cat in categories:
        cells = []
        for m in range(1, 13):
            ym = f"{year:04d}-{m:02d}"
            eff = effective_actual(db, cat, ym)
            cells.append({
                "year_month": ym,
                "effective": eff.amount,
                "source": eff.source,
                "transaction_sum": eff.transaction_sum,
                "manual_amount": eff.manual_amount,
                "budget": budget_for(db, cat.id, ym),
            })
        lines.append({
            "category_id": cat.id,
            "category_name": cat.name,
            "kind": cat.kind,
            "cells": cells,
        })
    return {"year": year, "lines": lines}


@router.post("/")
def upsert_actual(
    data: ManualActualUpsert,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Create or update the manual actual for one (category, month)."""
    _validate_ym(data.year_month)
    _require_category(db, data.category_id)

    existing = (
        db.query(ManualActual)
        .filter(
            ManualActual.category_id == data.category_id,
            ManualActual.year_month == data.year_month,
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
        ))
    db.commit()

    cat = _require_category(db, data.category_id)
    eff = effective_actual(db, cat, data.year_month)
    return {
        "category_id": cat.id,
        "year_month": data.year_month,
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

    for entry in data.entries:
        existing = (
            db.query(ManualActual)
            .filter(
                ManualActual.category_id == entry.category_id,
                ManualActual.year_month == entry.year_month,
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
            ))
    db.commit()
    return {"upserted": len(data.entries)}


@router.delete("/{category_id}/{year_month}", status_code=204)
def delete_actual(
    category_id: int,
    year_month: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Delete a manual actual, reverting the cell to transaction-derived."""
    _validate_ym(year_month)
    existing = (
        db.query(ManualActual)
        .filter(
            ManualActual.category_id == category_id,
            ManualActual.year_month == year_month,
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
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    _validate_ym(year_month)
    return month_totals(db, year_month).__dict__


@router.get("/year-summary")
def get_year_summary(
    year: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    summary = year_summary(db, year)
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
