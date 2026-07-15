"""WS-D: prove the dashboard, budgets/income pages, and reports all read the
same aggregation, so their saved/actual figures agree."""

from datetime import datetime

from app.models import Budget, Category, ManualActual
from app.services.aggregation import month_totals, year_summary


def _current_ym() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def _seed_month(db, ym: str):
    inc = Category(name="Salary", kind="income")
    exp = Category(name="Rent", kind="expense")
    db.add_all([inc, exp])
    db.flush()
    db.add_all([
        ManualActual(category_id=inc.id, year_month=ym, amount=6000.0),
        ManualActual(category_id=exp.id, year_month=ym, amount=2200.0),
        Budget(category_id=inc.id, monthly_limit=5800.0, year_month=ym),
        Budget(category_id=exp.id, monthly_limit=2000.0, year_month=ym),
    ])
    db.commit()


def test_dashboard_saved_matches_aggregation(client, db_session):
    ym = _current_ym()
    _seed_month(db_session, ym)

    resp = client.get("/api/dashboard/summary?months=1")
    assert resp.status_code == 200
    saved = resp.json()["saved"]

    mt = month_totals(db_session, ym)
    assert saved["month_saved_actual"] == mt.saved_actual == 3800.0
    assert saved["month_saved_budget"] == mt.saved_budget == 3800.0
    assert saved["month_income_actual"] == mt.income_actual == 6000.0
    assert saved["month_expense_actual"] == mt.expense_actual == 2200.0


def test_dashboard_and_month_totals_endpoint_agree(client, db_session):
    """Budgets/Income pages read /api/actuals/month-totals; dashboard reads the
    same aggregation — they must return identical figures."""
    ym = _current_ym()
    _seed_month(db_session, ym)

    dash = client.get("/api/dashboard/summary?months=1").json()["saved"]
    mt = client.get(f"/api/actuals/month-totals?year_month={ym}").json()

    assert dash["month_saved_actual"] == mt["saved_actual"]
    assert dash["month_income_actual"] == mt["income_actual"]
    assert dash["month_expense_actual"] == mt["expense_actual"]


def test_year_summary_ytd_equals_sum_of_months(db_session):
    """Reports' annual saved (year_summary) must equal the month-by-month rollup."""
    inc = Category(name="Salary", kind="income")
    exp = Category(name="Rent", kind="expense")
    db_session.add_all([inc, exp])
    db_session.flush()
    for m in range(1, 13):
        db_session.add_all([
            ManualActual(category_id=inc.id, year_month=f"2024-{m:02d}", amount=6000.0),
            ManualActual(category_id=exp.id, year_month=f"2024-{m:02d}", amount=2000.0),
        ])
    db_session.commit()

    ys = year_summary(db_session, 2024)  # past year -> full 12 months
    assert ys.ytd_through_month == 12
    summed = sum(month_totals(db_session, f"2024-{m:02d}").saved_actual for m in range(1, 13))
    assert round(ys.saved_actual_ytd, 2) == round(summed, 2) == 48000.0


def test_negative_saved_not_clamped(client, db_session):
    ym = _current_ym()
    inc = Category(name="Salary", kind="income")
    exp = Category(name="Rent", kind="expense")
    db_session.add_all([inc, exp])
    db_session.flush()
    db_session.add_all([
        ManualActual(category_id=inc.id, year_month=ym, amount=1000.0),
        ManualActual(category_id=exp.id, year_month=ym, amount=2500.0),
    ])
    db_session.commit()

    saved = client.get("/api/dashboard/summary?months=1").json()["saved"]
    assert saved["month_saved_actual"] == -1500.0
