from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, extract
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, Transaction
from app.schemas import DashboardSummary, TransactionOut

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    months: int = Query(default=1, ge=1, le=12),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    start_date = now - timedelta(days=months * 30)

    accounts = db.query(Account).filter(Account.is_active == True).all()
    total_balance = sum(a.current_balance for a in accounts)

    transactions = (
        db.query(Transaction)
        .filter(Transaction.date >= start_date)
        .order_by(Transaction.date.desc())
        .all()
    )

    total_income = sum(abs(t.amount) for t in transactions if t.amount < 0)
    total_expenses = sum(t.amount for t in transactions if t.amount > 0)
    net_cash_flow = total_income - total_expenses

    spending_by_category: dict[str, float] = {}
    for t in transactions:
        if t.amount > 0 and t.category:
            spending_by_category[t.category] = (
                spending_by_category.get(t.category, 0) + t.amount
            )

    monthly_trend = _compute_monthly_trend(db, months)

    recent = transactions[:10]

    return DashboardSummary(
        total_balance=round(total_balance, 2),
        total_income=round(total_income, 2),
        total_expenses=round(total_expenses, 2),
        net_cash_flow=round(net_cash_flow, 2),
        account_count=len(accounts),
        recent_transactions=[TransactionOut.model_validate(t) for t in recent],
        spending_by_category={k: round(v, 2) for k, v in spending_by_category.items()},
        monthly_trend=monthly_trend,
    )


def _compute_monthly_trend(db: Session, months: int) -> list[dict]:
    now = datetime.utcnow()
    trend = []

    for i in range(months - 1, -1, -1):
        month_start = (now - timedelta(days=i * 30)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        if i > 0:
            month_end = (now - timedelta(days=(i - 1) * 30)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
        else:
            month_end = now

        txns = (
            db.query(Transaction)
            .filter(Transaction.date >= month_start, Transaction.date < month_end)
            .all()
        )

        income = sum(abs(t.amount) for t in txns if t.amount < 0)
        expenses = sum(t.amount for t in txns if t.amount > 0)

        trend.append({
            "month": month_start.strftime("%Y-%m"),
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "net": round(income - expenses, 2),
        })

    return trend


@router.get("/balances")
def get_account_balances(db: Session = Depends(get_db)):
    accounts = db.query(Account).filter(Account.is_active == True).all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "type": a.account_type,
            "balance": round(a.current_balance, 2),
            "currency": a.currency,
        }
        for a in accounts
    ]


@router.get("/spending-breakdown")
def get_spending_breakdown(
    months: int = Query(default=1, ge=1, le=12),
    db: Session = Depends(get_db),
):
    start_date = datetime.utcnow() - timedelta(days=months * 30)

    transactions = (
        db.query(Transaction)
        .filter(Transaction.date >= start_date, Transaction.amount > 0)
        .all()
    )

    by_category: dict[str, float] = {}
    for t in transactions:
        cat = t.category or "Uncategorized"
        by_category[cat] = by_category.get(cat, 0) + t.amount

    return [
        {"category": k, "amount": round(v, 2)}
        for k, v in sorted(by_category.items(), key=lambda x: -x[1])
    ]
