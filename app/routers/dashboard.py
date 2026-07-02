from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, Transaction, Budget, Category, User
from app.schemas import DashboardSummary, TransactionOut
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _format_currency(amount: float) -> float:
    return round(amount, 2)


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    months: int = Query(default=1, ge=1, le=12),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    now = datetime.utcnow()
    start_date = (now - timedelta(days=months * 30)).date()

    accounts = db.query(Account).filter(Account.is_active == True).all()
    total_balance = sum(a.current_balance for a in accounts)

    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.date >= start_date,
            Transaction.review_status == "confirmed",
        )
        .order_by(Transaction.date.desc())
        .all()
    )

    total_income = sum(abs(t.amount) for t in transactions if t.amount < 0)
    total_expenses = sum(t.amount for t in transactions if t.amount > 0)
    net_cash_flow = total_income - total_expenses

    spending_by_category: dict[str, float] = {}
    for t in transactions:
        if t.amount > 0:
            cat_name = "Uncategorized"
            if t.category_id and t.category_rel:
                cat_name = t.category_rel.name
            spending_by_category[cat_name] = spending_by_category.get(cat_name, 0) + t.amount

    monthly_trend = _compute_monthly_trend(db, months)
    budget_status = _compute_budget_status(db)

    recent = transactions[:10]

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
    )


def _compute_monthly_trend(db: Session, months: int) -> list[dict]:
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

        txns = (
            db.query(Transaction)
            .filter(
                Transaction.date >= month_start,
                Transaction.date < month_end,
                Transaction.review_status == "confirmed",
            )
            .all()
        )

        income = sum(abs(t.amount) for t in txns if t.amount < 0)
        expenses = sum(t.amount for t in txns if t.amount > 0)

        trend.append({
            "month": month_start.strftime("%Y-%m"),
            "income": _format_currency(income),
            "expenses": _format_currency(expenses),
            "net": _format_currency(income - expenses),
        })

    return trend


def _compute_budget_status(db: Session) -> list[dict]:
    now = datetime.utcnow()
    current_month = now.strftime("%Y-%m")
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).date()

    budgets = (
        db.query(Budget)
        .filter(Budget.is_active == True)
        .all()
    )

    result = []
    for budget in budgets:
        if budget.year_month and budget.year_month != current_month:
            continue

        category = db.query(Category).filter(Category.id == budget.category_id).first()
        if not category:
            continue

        spent = sum(
            t.amount
            for t in db.query(Transaction).filter(
                Transaction.category_id == budget.category_id,
                Transaction.date >= month_start,
                Transaction.amount > 0,
                Transaction.review_status == "confirmed",
            ).all()
        )

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
