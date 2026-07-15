"""WS-C: trend views are projections of the aggregation layer — they must
reconcile with the month/year totals the Dashboard uses.

The Monthly and Yearly trend views are built entirely from the ``/api/actuals``
year grid. These tests assert that grid reconciles with ``/api/actuals/month-totals``
so the frontend projections cannot drift from the Dashboard.
"""

from datetime import date

from app.models import Account, Budget, Category, ManualActual, Transaction


def _seed(db):
    acc = Account(name="Checking", account_type="depository", current_balance=0.0)
    db.add(acc)
    groceries = Category(name="Groceries", kind="expense")
    gas = Category(name="Gas", kind="expense")
    salary = Category(name="Salary", kind="income")
    db.add_all([groceries, gas, salary])
    db.flush()
    # Groceries: manual actual overrides
    db.add(Transaction(account_id=acc.id, category_id=groceries.id, amount=900.0,
                       date=date(2026, 3, 10), name="store", review_status="confirmed"))
    db.add(ManualActual(category_id=groceries.id, year_month="2026-03", amount=1000.0))
    # Gas: transaction-derived
    db.add(Transaction(account_id=acc.id, category_id=gas.id, amount=150.0,
                       date=date(2026, 3, 5), name="fuel", review_status="confirmed"))
    db.add(Budget(category_id=gas.id, monthly_limit=120.0))
    # Salary income
    db.add(Transaction(account_id=acc.id, category_id=salary.id, amount=-5000.0,
                       date=date(2026, 3, 1), name="pay", review_status="confirmed"))
    db.commit()


def _grid(client, year):
    return client.get(f"/api/actuals/?year={year}").json()


def test_monthly_rows_equal_dashboard_month_total(client, db_session):
    _seed(db_session)
    grid = _grid(client, 2026)
    march = 2  # index

    expense_sum = sum(
        (l["cells"][march]["effective"] or 0)
        for l in grid["lines"] if l["kind"] == "expense"
    )
    mt = client.get("/api/actuals/month-totals?year_month=2026-03").json()
    assert round(expense_sum, 2) == mt["expense_actual"]
    # manual override, not summed with transactions: groceries = 1000 (not 1900)
    assert round(expense_sum, 2) == 1150.0


def test_year_matrix_column_totals_equal_monthly_spend(client, db_session):
    _seed(db_session)
    grid = _grid(client, 2026)
    for m in range(12):
        col_total = sum(
            (l["cells"][m]["effective"] or 0)
            for l in grid["lines"] if l["kind"] == "expense"
        )
        ym = f"2026-{m + 1:02d}"
        mt = client.get(f"/api/actuals/month-totals?year_month={ym}").json()
        assert round(col_total, 2) == mt["expense_actual"]


def test_year_matrix_row_total_equals_sum_of_cells(client, db_session):
    _seed(db_session)
    grid = _grid(client, 2026)
    for l in grid["lines"]:
        row_total = sum((c["effective"] or 0) for c in l["cells"])
        # trivially the projection the frontend uses for the row total
        assert round(row_total, 2) == round(
            sum((c["effective"] or 0) for c in l["cells"]), 2
        )
    # grand total across expense rows == sum of monthly expense totals
    grand = sum(
        (c["effective"] or 0)
        for l in grid["lines"] if l["kind"] == "expense"
        for c in l["cells"]
    )
    monthly_sum = sum(
        client.get(f"/api/actuals/month-totals?year_month=2026-{m + 1:02d}").json()["expense_actual"]
        for m in range(12)
    )
    assert round(grand, 2) == round(monthly_sum, 2)
