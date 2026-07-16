"""Single source of truth for effective actuals, budgets, and saved totals.

Dashboard, budgets page, income page, and reports all read from here so a
figure is computed exactly once. See INVARIANTS.md:

- For any line-month there is exactly one effective actual, produced by
  ``effective_actual`` applying the reconciliation rule; manual and
  transaction-derived values are never summed together.
- Saved is always derived (income - expenses); never stored.
"""

import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Budget, Category, ManualActual, Transaction

_YM_RE = re.compile(r"^\d{4}-\d{2}$")


def is_valid_year_month(year_month: str) -> bool:
    if not _YM_RE.match(year_month):
        return False
    month = int(year_month[5:7])
    return 1 <= month <= 12


def month_bounds(year_month: str) -> tuple[date, date]:
    """Return (first_day, last_day) for a 'YYYY-MM' string."""
    y, m = int(year_month[:4]), int(year_month[5:7])
    _, last = monthrange(y, m)
    return date(y, m, 1), date(y, m, last)


@dataclass
class EffectiveActual:
    """The one actual for a (category, month) plus the reference values."""

    amount: Optional[float]        # effective actual; None = empty cell
    source: str                    # 'manual' | 'transactions' | 'none'
    transaction_sum: float         # always computable; reference beside manual
    manual_amount: Optional[float]  # the manual value if one exists


def transaction_sum(db: Session, category: Category, year_month: str) -> float:
    """Confirmed-transaction actual for a category in a month.

    Sign follows the category kind: expense = sum of positive amounts,
    income = sum of the absolute value of negative amounts. Transfers are
    excluded (they double-count). Always returned non-negative.
    """
    start, end = month_bounds(year_month)
    txns = (
        db.query(Transaction)
        .filter(
            Transaction.category_id == category.id,
            Transaction.date >= start,
            Transaction.date <= end,
            Transaction.review_status == "confirmed",
            Transaction.txn_type != "transfer",
        )
        .all()
    )
    if category.kind == "income":
        return round(sum(-t.amount for t in txns if t.amount < 0), 2)
    return round(sum(t.amount for t in txns if t.amount > 0), 2)


def effective_actual(db: Session, category: Category, year_month: str) -> EffectiveActual:
    """Apply the reconciliation rule for one (category, month).

    A manual actual, if present, is THE actual; the transaction sum stays
    retrievable beside it. Otherwise the transaction sum is the actual. If
    neither exists the cell is empty. Never manual + transactions.
    """
    txn_sum = transaction_sum(db, category, year_month)
    manual = (
        db.query(ManualActual)
        .filter(
            ManualActual.category_id == category.id,
            ManualActual.year_month == year_month,
        )
        .first()
    )
    if manual is not None:
        return EffectiveActual(
            amount=round(manual.amount, 2),
            source="manual",
            transaction_sum=txn_sum,
            manual_amount=round(manual.amount, 2),
        )
    if txn_sum != 0:
        return EffectiveActual(
            amount=txn_sum, source="transactions", transaction_sum=txn_sum, manual_amount=None
        )
    return EffectiveActual(amount=None, source="none", transaction_sum=0.0, manual_amount=None)


def budget_for(db: Session, category_id: int, year_month: str) -> Optional[float]:
    """The budget for a category in a month.

    A month-specific (dated) budget wins; otherwise the every-month
    (``year_month IS NULL``) budget is the default for that month.
    """
    dated = (
        db.query(Budget)
        .filter(
            Budget.category_id == category_id,
            Budget.is_active == True,  # noqa: E712
            Budget.year_month == year_month,
        )
        .first()
    )
    if dated is not None:
        return round(dated.monthly_limit, 2)
    every_month = (
        db.query(Budget)
        .filter(
            Budget.category_id == category_id,
            Budget.is_active == True,  # noqa: E712
            Budget.year_month.is_(None),
        )
        .first()
    )
    if every_month is not None:
        return round(every_month.monthly_limit, 2)
    return None


def year_grid(db: Session, year: int) -> list[dict]:
    """Batched full-year grid: every category x 12 months, in a constant
    number of queries (no per-cell round trips).

    Returns the same per-line/per-cell shape as the per-cell path so the API
    response is byte-for-byte compatible; ``effective_actual``/``budget_for``
    stay as the single-cell source of truth for other callers.
    """
    categories = db.query(Category).order_by(Category.name).all()
    year_prefix = f"{year:04d}-"
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)

    # 1 query: all confirmed, non-transfer transactions in the year.
    pos: dict[tuple[int, int], float] = {}   # (category_id, month) -> sum(amount>0)
    negabs: dict[tuple[int, int], float] = {}  # (category_id, month) -> sum(-amount, amount<0)
    txns = (
        db.query(
            Transaction.category_id,
            Transaction.date,
            Transaction.amount,
        )
        .filter(
            Transaction.category_id.isnot(None),
            Transaction.date >= year_start,
            Transaction.date <= year_end,
            Transaction.review_status == "confirmed",
            Transaction.txn_type != "transfer",
        )
        .all()
    )
    for cat_id, txn_date, amount in txns:
        key = (cat_id, txn_date.month)
        if amount > 0:
            pos[key] = pos.get(key, 0.0) + amount
        elif amount < 0:
            negabs[key] = negabs.get(key, 0.0) + (-amount)

    # 1 query: all manual actuals for the year.
    manuals: dict[tuple[int, str], float] = {}
    for cat_id, ym, amount in (
        db.query(ManualActual.category_id, ManualActual.year_month, ManualActual.amount)
        .filter(ManualActual.year_month.like(f"{year_prefix}%"))
        .all()
    ):
        manuals[(cat_id, ym)] = amount

    # 1 query: all active budgets (dated in-year + every-month NULL rows).
    dated_budgets: dict[tuple[int, str], float] = {}
    every_month_budgets: dict[int, float] = {}
    for cat_id, ym, limit in (
        db.query(Budget.category_id, Budget.year_month, Budget.monthly_limit)
        .filter(Budget.is_active == True)  # noqa: E712
        .all()
    ):
        if ym is None:
            every_month_budgets.setdefault(cat_id, limit)
        elif ym.startswith(year_prefix):
            dated_budgets[(cat_id, ym)] = limit

    lines = []
    for cat in categories:
        cells = []
        for m in range(1, 13):
            ym = f"{year:04d}-{m:02d}"
            txn_sum = round(
                (negabs.get((cat.id, m), 0.0) if cat.kind == "income" else pos.get((cat.id, m), 0.0)),
                2,
            )
            manual = manuals.get((cat.id, ym))
            if manual is not None:
                effective, source, manual_amount = round(manual, 2), "manual", round(manual, 2)
            elif txn_sum != 0:
                effective, source, manual_amount = txn_sum, "transactions", None
            else:
                effective, source, manual_amount = None, "none", None

            if (cat.id, ym) in dated_budgets:
                budget = round(dated_budgets[(cat.id, ym)], 2)
            elif cat.id in every_month_budgets:
                budget = round(every_month_budgets[cat.id], 2)
            else:
                budget = None

            cells.append({
                "year_month": ym,
                "effective": effective,
                "source": source,
                "transaction_sum": txn_sum,
                "manual_amount": manual_amount,
                "budget": budget,
            })
        lines.append({
            "category_id": cat.id,
            "category_name": cat.name,
            "kind": cat.kind,
            "cells": cells,
        })
    return lines


@dataclass
class MonthTotals:
    year_month: str
    income_actual: float
    expense_actual: float
    income_budget: float
    expense_budget: float
    saved_actual: float
    saved_budget: float


def month_totals(db: Session, year_month: str) -> MonthTotals:
    """Aggregate every category into income/expense actual & budget totals.

    Saved (actual) = income_actual - expense_actual.
    Saved (budget) = income_budget - expense_budget.
    """
    categories = db.query(Category).all()
    income_actual = expense_actual = 0.0
    income_budget = expense_budget = 0.0

    for cat in categories:
        eff = effective_actual(db, cat, year_month)
        actual = eff.amount or 0.0
        budget = budget_for(db, cat.id, year_month) or 0.0
        if cat.kind == "income":
            income_actual += actual
            income_budget += budget
        else:
            expense_actual += actual
            expense_budget += budget

    return MonthTotals(
        year_month=year_month,
        income_actual=round(income_actual, 2),
        expense_actual=round(expense_actual, 2),
        income_budget=round(income_budget, 2),
        expense_budget=round(expense_budget, 2),
        saved_actual=round(income_actual - expense_actual, 2),
        saved_budget=round(income_budget - expense_budget, 2),
    )


@dataclass
class YearSummary:
    year: int
    months: list[MonthTotals]
    # Full-year budget plan
    saved_budget_year: float
    income_budget_year: float
    expense_budget_year: float
    # Year-to-date actuals (through the current month for the current year;
    # all 12 months otherwise). Kept separate from full-year budget so the two
    # are never blended into one misleading number.
    saved_actual_ytd: float
    income_actual_ytd: float
    expense_actual_ytd: float
    ytd_through_month: int  # 1..12


def year_summary(db: Session, year: int, today: Optional[date] = None) -> YearSummary:
    today = today or datetime.utcnow().date()
    if year < today.year:
        ytd_through = 12
    elif year > today.year:
        ytd_through = 0
    else:
        ytd_through = today.month

    months: list[MonthTotals] = []
    saved_budget_year = income_budget_year = expense_budget_year = 0.0
    saved_actual_ytd = income_actual_ytd = expense_actual_ytd = 0.0

    for m in range(1, 13):
        ym = f"{year:04d}-{m:02d}"
        mt = month_totals(db, ym)
        months.append(mt)
        saved_budget_year += mt.saved_budget
        income_budget_year += mt.income_budget
        expense_budget_year += mt.expense_budget
        if m <= ytd_through:
            saved_actual_ytd += mt.saved_actual
            income_actual_ytd += mt.income_actual
            expense_actual_ytd += mt.expense_actual

    return YearSummary(
        year=year,
        months=months,
        saved_budget_year=round(saved_budget_year, 2),
        income_budget_year=round(income_budget_year, 2),
        expense_budget_year=round(expense_budget_year, 2),
        saved_actual_ytd=round(saved_actual_ytd, 2),
        income_actual_ytd=round(income_actual_ytd, 2),
        expense_actual_ytd=round(expense_actual_ytd, 2),
        ytd_through_month=ytd_through,
    )
