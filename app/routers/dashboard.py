from typing import NamedTuple, Optional

from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, Transaction, TransactionSplit, Budget, Category, Entity, User
from app.schemas import DashboardSummary, SavedSummary, TransactionOut
from app.services.aggregation import month_totals, year_summary
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _format_currency(amount: float) -> float:
    return round(amount, 2)


class Contribution(NamedTuple):
    amount: float
    category_id: Optional[int]
    category_name: str


def _entity_contributions(
    db: Session,
    start_date: date,
    end_date: Optional[date],
    entity_id: Optional[int],
    category_id: Optional[int] = None,
) -> list[Contribution]:
    """Confirmed contributions over ``[start_date, end_date)`` for an entity.

    ``entity_id=None`` is the unscoped "All" view: every confirmed transaction
    at its full amount. For a specific entity the amount attributed is the
    direct transaction amount for txns it owns, plus split allocations to it
    from txns owned by another/no entity — never both for the same txn, so a
    transaction split across entities is not double counted.
    """
    def date_filter(q):
        q = q.filter(Transaction.date >= start_date, Transaction.review_status == "confirmed")
        if end_date is not None:
            q = q.filter(Transaction.date < end_date)
        return q

    def cat_name(cat: Optional[Category]) -> str:
        return cat.name if cat is not None else "Uncategorized"

    if entity_id is None:
        q = date_filter(db.query(Transaction))
        if category_id is not None:
            q = q.filter(Transaction.category_id == category_id)
        return [Contribution(t.amount, t.category_id, cat_name(t.category_rel)) for t in q.all()]

    direct_q = date_filter(db.query(Transaction)).filter(Transaction.entity_id == entity_id)
    if category_id is not None:
        direct_q = direct_q.filter(Transaction.category_id == category_id)
    out = [Contribution(t.amount, t.category_id, cat_name(t.category_rel)) for t in direct_q.all()]

    split_q = date_filter(
        db.query(TransactionSplit, Transaction).join(
            Transaction, TransactionSplit.transaction_id == Transaction.id
        )
    ).filter(
        TransactionSplit.entity_id == entity_id,
        or_(Transaction.entity_id.is_(None), Transaction.entity_id != entity_id),
    )
    if category_id is not None:
        split_q = split_q.filter(Transaction.category_id == category_id)
    for split, txn in split_q.all():
        out.append(Contribution(split.amount, txn.category_id, cat_name(txn.category_rel)))
    return out


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    months: int = Query(default=1, ge=1, le=12),
    entity_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    now = datetime.utcnow()
    start_date = (now - timedelta(days=months * 30)).date()

    accounts = db.query(Account).filter(Account.is_active == True).all()
    total_balance = sum(a.current_balance for a in accounts)

    contributions = _entity_contributions(db, start_date, None, entity_id)

    total_income = sum(-c.amount for c in contributions if c.amount < 0)
    total_expenses = sum(c.amount for c in contributions if c.amount > 0)
    net_cash_flow = total_income - total_expenses

    spending_by_category: dict[str, float] = {}
    for c in contributions:
        if c.amount > 0:
            spending_by_category[c.category_name] = (
                spending_by_category.get(c.category_name, 0) + c.amount
            )

    monthly_trend = _compute_monthly_trend(db, months, entity_id)
    budget_status = _compute_budget_status(db, entity_id)
    saved = _compute_saved(db, now.date(), entity_id)

    recent = _recent_transactions(db, start_date, entity_id)

    return DashboardSummary(
        total_balance=_format_currency(total_balance),
        total_income=_format_currency(total_income),
        total_expenses=_format_currency(total_expenses),
        net_cash_flow=_format_currency(net_cash_flow),
        account_count=len(accounts),
        recent_transactions=[TransactionOut.model_validate(t) for t in recent],
        spending_by_category={k: _format_currency(v) for k, v in spending_by_category.items()},
        monthly_trend=monthly_trend,
        budget_status=budget_status,
        saved=saved,
    )


def _recent_transactions(
    db: Session, start_date: date, entity_id: Optional[int]
) -> list[Transaction]:
    """Up to 10 most recent confirmed transactions relevant to the entity view."""
    q = db.query(Transaction).filter(
        Transaction.date >= start_date,
        Transaction.review_status == "confirmed",
    )
    if entity_id is not None:
        split_ids = (
            db.query(TransactionSplit.transaction_id)
            .filter(TransactionSplit.entity_id == entity_id)
            .scalar_subquery()
        )
        q = q.filter(
            or_(Transaction.entity_id == entity_id, Transaction.id.in_(split_ids))
        )
    return q.order_by(Transaction.date.desc()).limit(10).all()


def _compute_saved(
    db: Session, today: date, entity_id: Optional[int] = None
) -> SavedSummary:
    """Total-saved header figures via the shared aggregation (income - expenses).

    Reads the same ``effective_actual`` path as the Budgets/Income pages so all
    three surfaces agree. Current-year YTD actual is kept separate from the
    full-year budgeted saved. Negative saved is preserved (overspent), not clamped.
    """
    year_month = today.strftime("%Y-%m")
    mt = month_totals(db, year_month, entity_id)
    ys = year_summary(db, today.year, today=today, entity_id=entity_id)
    return SavedSummary(
        year_month=year_month,
        month_income_actual=_format_currency(mt.income_actual),
        month_expense_actual=_format_currency(mt.expense_actual),
        month_saved_actual=_format_currency(mt.saved_actual),
        month_saved_budget=_format_currency(mt.saved_budget),
        ytd_saved_actual=_format_currency(ys.saved_actual_ytd),
        ytd_through_month=ys.ytd_through_month,
        year_saved_budget=_format_currency(ys.saved_budget_year),
    )


def _compute_monthly_trend(db: Session, months: int, entity_id: Optional[int] = None) -> list[dict]:
    now = datetime.utcnow()
    trend = []

    for i in range(months - 1, -1, -1):
        month_start = (now - timedelta(days=i * 30)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).date()
        if i > 0:
            month_end = (now - timedelta(days=(i - 1) * 30)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            ).date()
        else:
            month_end = now.date()

        contributions = _entity_contributions(db, month_start, month_end, entity_id)

        income = sum(-c.amount for c in contributions if c.amount < 0)
        expenses = sum(c.amount for c in contributions if c.amount > 0)

        trend.append({
            "month": month_start.strftime("%Y-%m"),
            "income": _format_currency(income),
            "expenses": _format_currency(expenses),
            "net": _format_currency(income - expenses),
        })

    return trend


def _compute_budget_status(db: Session, entity_id: Optional[int] = None) -> list[dict]:
    now = datetime.utcnow()
    current_month = now.strftime("%Y-%m")
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).date()

    budget_q = db.query(Budget).filter(Budget.is_active == True)
    if entity_id is not None:
        budget_q = budget_q.filter(Budget.entity_id == entity_id)
    budgets = budget_q.all()

    result = []
    for budget in budgets:
        if budget.year_month and budget.year_month != current_month:
            continue

        category = db.query(Category).filter(Category.id == budget.category_id).first()
        if not category:
            continue

        contributions = _entity_contributions(
            db, month_start, None, entity_id, category_id=budget.category_id
        )
        spent = sum(c.amount for c in contributions if c.amount > 0)

        result.append({
            "category": category.name,
            "budget": _format_currency(budget.monthly_limit),
            "spent": _format_currency(spent),
            "remaining": _format_currency(budget.monthly_limit - spent),
            "percent_used": round(spent / budget.monthly_limit * 100, 1) if budget.monthly_limit > 0 else 0,
        })

    return result


@router.get("/balances")
def get_account_balances(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    accounts = db.query(Account).filter(Account.is_active == True).all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "type": a.account_type,
            "balance": _format_currency(a.current_balance),
            "currency": a.currency,
        }
        for a in accounts
    ]


@router.get("/entity-breakdown")
def get_entity_breakdown(
    months: int = Query(default=1, ge=1, le=12),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Per-entity income/expenses/net for the given period."""
    now = datetime.utcnow()
    start_date = (now - timedelta(days=months * 30)).date()

    entities = db.query(Entity).filter(Entity.is_active == True).all()
    result = []

    for entity in entities:
        contributions = _entity_contributions(db, start_date, None, entity.id)
        income = sum(-c.amount for c in contributions if c.amount < 0)
        expenses = sum(c.amount for c in contributions if c.amount > 0)

        result.append({
            "entity_id": entity.id,
            "entity_name": entity.name,
            "entity_type": entity.entity_type,
            "color": entity.color,
            "income": _format_currency(income),
            "expenses": _format_currency(expenses),
            "net": _format_currency(income - expenses),
        })

    return result
