"""Tests for manual actuals, income-kind categories, and saved totals (WS-A)."""

from datetime import date

from app.models import Account, Budget, Category, ManualActual, Transaction
from app.services.aggregation import (
    budget_for,
    effective_actual,
    month_totals,
    transaction_sum,
    year_summary,
)


def _account(db):
    acc = Account(name="Checking", account_type="depository", current_balance=0.0)
    db.add(acc)
    db.flush()
    return acc


def _txn(db, account_id, category_id, amount, d, txn_type="expense"):
    db.add(Transaction(
        account_id=account_id,
        category_id=category_id,
        amount=amount,
        date=d,
        name="t",
        txn_type=txn_type,
        review_status="confirmed",
    ))


# ---- effective actual / reconciliation ----

def test_manual_actual_overrides_transaction_sum(db_session):
    acc = _account(db_session)
    cat = Category(name="Groceries", kind="expense")
    db_session.add(cat)
    db_session.flush()
    _txn(db_session, acc.id, cat.id, 1012.0, date(2026, 7, 10))
    db_session.add(ManualActual(category_id=cat.id, year_month="2026-07", amount=1050.0))
    db_session.commit()

    eff = effective_actual(db_session, cat, "2026-07")
    assert eff.amount == 1050.0
    assert eff.source == "manual"
    assert eff.transaction_sum == 1012.0  # still retrievable beside it


def test_no_manual_uses_transaction_sum(db_session):
    acc = _account(db_session)
    cat = Category(name="Gas", kind="expense")
    db_session.add(cat)
    db_session.flush()
    _txn(db_session, acc.id, cat.id, 40.0, date(2026, 7, 3))
    _txn(db_session, acc.id, cat.id, 60.0, date(2026, 7, 20))
    db_session.commit()

    eff = effective_actual(db_session, cat, "2026-07")
    assert eff.amount == 100.0
    assert eff.source == "transactions"


def test_empty_cell_when_no_data(db_session):
    cat = Category(name="Travel", kind="expense")
    db_session.add(cat)
    db_session.commit()
    eff = effective_actual(db_session, cat, "2026-07")
    assert eff.amount is None
    assert eff.source == "none"


def test_transfers_excluded(db_session):
    acc = _account(db_session)
    cat = Category(name="Misc", kind="expense")
    db_session.add(cat)
    db_session.flush()
    _txn(db_session, acc.id, cat.id, 500.0, date(2026, 7, 5), txn_type="transfer")
    db_session.commit()
    assert transaction_sum(db_session, cat, "2026-07") == 0.0


def test_income_transaction_sum_uses_abs_of_negative(db_session):
    acc = _account(db_session)
    cat = Category(name="Salary", kind="income")
    db_session.add(cat)
    db_session.flush()
    _txn(db_session, acc.id, cat.id, -5000.0, date(2026, 7, 1), txn_type="income")
    db_session.commit()
    assert transaction_sum(db_session, cat, "2026-07") == 5000.0


# ---- month totals & saved ----

def test_month_totals_saved(db_session):
    cat_inc = Category(name="Salary", kind="income")
    cat_exp = Category(name="Rent", kind="expense")
    db_session.add_all([cat_inc, cat_exp])
    db_session.flush()
    db_session.add_all([
        ManualActual(category_id=cat_inc.id, year_month="2026-07", amount=6000.0),
        ManualActual(category_id=cat_exp.id, year_month="2026-07", amount=2200.0),
        Budget(category_id=cat_inc.id, monthly_limit=5800.0, year_month="2026-07"),
        Budget(category_id=cat_exp.id, monthly_limit=2000.0, year_month="2026-07"),
    ])
    db_session.commit()

    mt = month_totals(db_session, "2026-07")
    assert mt.income_actual == 6000.0
    assert mt.expense_actual == 2200.0
    assert mt.saved_actual == 3800.0
    assert mt.saved_budget == 3800.0  # 5800 - 2000


def test_month_totals_negative_saved(db_session):
    cat_inc = Category(name="Salary", kind="income")
    cat_exp = Category(name="Rent", kind="expense")
    db_session.add_all([cat_inc, cat_exp])
    db_session.flush()
    db_session.add_all([
        ManualActual(category_id=cat_inc.id, year_month="2026-07", amount=1000.0),
        ManualActual(category_id=cat_exp.id, year_month="2026-07", amount=2200.0),
    ])
    db_session.commit()
    mt = month_totals(db_session, "2026-07")
    assert mt.saved_actual == -1200.0


def test_budget_fallback_every_month(db_session):
    cat = Category(name="Gas", kind="expense")
    db_session.add(cat)
    db_session.flush()
    # every-month budget (year_month NULL) applies to any month with no dated row
    db_session.add(Budget(category_id=cat.id, monthly_limit=210.0, year_month=None))
    db_session.commit()
    mt = month_totals(db_session, "2026-03")
    assert mt.expense_budget == 210.0


def test_year_summary_ytd_vs_full_year(db_session):
    cat_exp = Category(name="Rent", kind="expense")
    db_session.add(cat_exp)
    db_session.flush()
    # budget every month; actual only for Jan
    db_session.add(Budget(category_id=cat_exp.id, monthly_limit=2000.0, year_month=None))
    db_session.add(ManualActual(category_id=cat_exp.id, year_month="2025-01", amount=1900.0))
    db_session.commit()

    summary = year_summary(db_session, 2025, today=date(2026, 7, 1))
    assert len(summary.months) == 12
    assert summary.ytd_through_month == 12  # past year -> full year
    assert summary.expense_budget_year == 24000.0
    assert summary.expense_actual_ytd == 1900.0


# ---- endpoints ----

def test_upsert_and_effective_endpoint(client, db_session):
    cat = Category(name="Groceries", kind="expense")
    db_session.add(cat)
    db_session.commit()
    resp = client.post("/api/actuals/", json={
        "category_id": cat.id, "year_month": "2026-07", "amount": 1050.0,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["effective"] == 1050.0
    assert body["source"] == "manual"


def test_delete_reverts_to_transactions(client, db_session):
    acc = _account(db_session)
    cat = Category(name="Groceries", kind="expense")
    db_session.add(cat)
    db_session.flush()
    _txn(db_session, acc.id, cat.id, 1012.0, date(2026, 7, 10))
    db_session.add(ManualActual(category_id=cat.id, year_month="2026-07", amount=1050.0))
    db_session.commit()

    resp = client.delete(f"/api/actuals/{cat.id}/2026-07")
    assert resp.status_code == 204
    eff = effective_actual(db_session, cat, "2026-07")
    assert eff.source == "transactions"
    assert eff.amount == 1012.0


def test_income_line_accepts_budget_and_actual_same_endpoints(client, db_session):
    cat = Category(name="Salary", kind="income")
    db_session.add(cat)
    db_session.commit()
    resp = client.post("/api/actuals/", json={
        "category_id": cat.id, "year_month": "2026-07", "amount": 6000.0,
    })
    assert resp.status_code == 200
    assert resp.json()["effective"] == 6000.0


def test_bulk_upsert_atomic(client, db_session):
    cat = Category(name="Groceries", kind="expense")
    db_session.add(cat)
    db_session.commit()
    # one bad entry (nonexistent category) -> whole batch rejected, nothing committed
    resp = client.post("/api/actuals/bulk", json={"entries": [
        {"category_id": cat.id, "year_month": "2026-01", "amount": 100.0},
        {"category_id": 99999, "year_month": "2026-02", "amount": 200.0},
    ]})
    assert resp.status_code == 404
    assert db_session.query(ManualActual).count() == 0


def test_bulk_upsert_twelve_months(client, db_session):
    cat = Category(name="Groceries", kind="expense")
    db_session.add(cat)
    db_session.commit()
    entries = [
        {"category_id": cat.id, "year_month": f"2026-{m:02d}", "amount": 100.0 * m}
        for m in range(1, 13)
    ]
    resp = client.post("/api/actuals/bulk", json={"entries": entries})
    assert resp.status_code == 200
    assert db_session.query(ManualActual).count() == 12


def test_upsert_rejects_bad_year_month(client, db_session):
    cat = Category(name="Groceries", kind="expense")
    db_session.add(cat)
    db_session.commit()
    resp = client.post("/api/actuals/", json={
        "category_id": cat.id, "year_month": "2026/07", "amount": 100.0,
    })
    assert resp.status_code == 422


def test_upsert_rejects_negative_amount(client, db_session):
    cat = Category(name="Groceries", kind="expense")
    db_session.add(cat)
    db_session.commit()
    resp = client.post("/api/actuals/", json={
        "category_id": cat.id, "year_month": "2026-07", "amount": -5.0,
    })
    assert resp.status_code == 422


# ---- budget month upsert / fill-forward ----

def test_budget_upsert_creates_then_updates_same_row(client, db_session):
    cat = Category(name="Groceries", kind="expense")
    db_session.add(cat)
    db_session.commit()
    r1 = client.post("/api/budgets/upsert", json={
        "category_id": cat.id, "year_month": "2026-07", "monthly_limit": 800.0,
    })
    assert r1.status_code == 200
    r2 = client.post("/api/budgets/upsert", json={
        "category_id": cat.id, "year_month": "2026-07", "monthly_limit": 900.0,
    })
    assert r2.status_code == 200
    assert budget_for(db_session, cat.id, "2026-07") == 900.0
    assert db_session.query(Budget).filter(
        Budget.category_id == cat.id, Budget.year_month == "2026-07"
    ).count() == 1


def test_budget_fill_forward(client, db_session):
    cat = Category(name="Groceries", kind="expense")
    db_session.add(cat)
    db_session.commit()
    resp = client.post("/api/budgets/fill-forward", json={
        "category_id": cat.id, "from_year_month": "2026-05", "monthly_limit": 700.0,
    })
    assert resp.status_code == 200
    assert resp.json()["updated"] == 8  # May..Dec
    assert budget_for(db_session, cat.id, "2026-05") == 700.0
    assert budget_for(db_session, cat.id, "2026-12") == 700.0
    assert budget_for(db_session, cat.id, "2026-04") is None  # past month untouched


def test_budget_upsert_bad_year_month(client, db_session):
    cat = Category(name="Groceries", kind="expense")
    db_session.add(cat)
    db_session.commit()
    resp = client.post("/api/budgets/upsert", json={
        "category_id": cat.id, "year_month": "2026-13", "monthly_limit": 100.0,
    })
    assert resp.status_code == 422
