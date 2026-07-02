from datetime import date, datetime

import pytest

from app.models import Account, Transaction, Category, Budget


def _setup_data(db):
    acct = Account(name="Chequing", account_type="checking", current_balance=5000.0)
    db.add(acct)
    db.flush()

    groceries = Category(name="Groceries", is_system=True)
    dining = Category(name="Dining", is_system=True)
    db.add_all([groceries, dining])
    db.flush()

    budget = Budget(category_id=groceries.id, monthly_limit=500.0)
    db.add(budget)

    today = date.today()
    transactions = [
        Transaction(
            account_id=acct.id, amount=150.0, date=today, name="Superstore",
            category_id=groceries.id, review_status="confirmed", review_source="manual",
            dedup_hash=Transaction.compute_dedup_hash(today, 150.0, "Superstore", acct.id),
        ),
        Transaction(
            account_id=acct.id, amount=75.0, date=today, name="Costco",
            category_id=groceries.id, review_status="confirmed", review_source="manual",
            dedup_hash=Transaction.compute_dedup_hash(today, 75.0, "Costco", acct.id),
        ),
        Transaction(
            account_id=acct.id, amount=45.0, date=today, name="Restaurant",
            category_id=dining.id, review_status="confirmed", review_source="manual",
            dedup_hash=Transaction.compute_dedup_hash(today, 45.0, "Restaurant", acct.id),
        ),
        Transaction(
            account_id=acct.id, amount=-3000.0, date=today, name="Salary",
            review_status="confirmed", review_source="manual",
            dedup_hash=Transaction.compute_dedup_hash(today, -3000.0, "Salary", acct.id),
        ),
        # Pending review — should NOT be included in analytics
        Transaction(
            account_id=acct.id, amount=200.0, date=today, name="Unknown Charge",
            review_status="pending", review_source="ai_parsed",
            dedup_hash=Transaction.compute_dedup_hash(today, 200.0, "Unknown Charge", acct.id),
        ),
    ]
    db.add_all(transactions)
    db.commit()
    return acct, groceries, dining, budget


def test_income_and_expense_calculation(db_session):
    acct, groceries, dining, budget = _setup_data(db_session)

    confirmed = db_session.query(Transaction).filter(
        Transaction.review_status == "confirmed"
    ).all()

    income = sum(abs(t.amount) for t in confirmed if t.amount < 0)
    expenses = sum(t.amount for t in confirmed if t.amount > 0)

    assert income == 3000.0
    assert expenses == 270.0  # 150 + 75 + 45


def test_pending_excluded_from_analytics(db_session):
    _setup_data(db_session)

    confirmed = db_session.query(Transaction).filter(
        Transaction.review_status == "confirmed"
    ).all()

    assert len(confirmed) == 4

    all_txns = db_session.query(Transaction).all()
    assert len(all_txns) == 5


def test_spending_by_category(db_session):
    acct, groceries, dining, budget = _setup_data(db_session)

    confirmed_expenses = db_session.query(Transaction).filter(
        Transaction.review_status == "confirmed",
        Transaction.amount > 0,
    ).all()

    by_category = {}
    for t in confirmed_expenses:
        cat_name = "Uncategorized"
        if t.category_id:
            cat = db_session.query(Category).filter(Category.id == t.category_id).first()
            if cat:
                cat_name = cat.name
        by_category[cat_name] = by_category.get(cat_name, 0) + t.amount

    assert by_category["Groceries"] == 225.0  # 150 + 75
    assert by_category["Dining"] == 45.0


def test_budget_vs_actual(db_session):
    acct, groceries, dining, budget = _setup_data(db_session)

    today = date.today()
    month_start = today.replace(day=1)

    grocery_spend = sum(
        t.amount
        for t in db_session.query(Transaction).filter(
            Transaction.category_id == groceries.id,
            Transaction.date >= month_start,
            Transaction.amount > 0,
            Transaction.review_status == "confirmed",
        ).all()
    )

    assert grocery_spend == 225.0
    assert budget.monthly_limit == 500.0
    remaining = budget.monthly_limit - grocery_spend
    assert remaining == 275.0
    percent_used = round(grocery_spend / budget.monthly_limit * 100, 1)
    assert percent_used == 45.0


def test_net_cash_flow(db_session):
    _setup_data(db_session)

    confirmed = db_session.query(Transaction).filter(
        Transaction.review_status == "confirmed"
    ).all()

    income = sum(abs(t.amount) for t in confirmed if t.amount < 0)
    expenses = sum(t.amount for t in confirmed if t.amount > 0)
    net = income - expenses

    assert net == 2730.0  # 3000 - 270
