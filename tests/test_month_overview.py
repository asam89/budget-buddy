"""Month overview: like-for-like variance, projections and a partly entered month."""

from app.models import Budget, Category, Entity, ManualActual
from app.services.aggregation import month_overview

YM = "2026-11"


def _setup(db):
    p = Entity(name="Personal", entity_type="personal", is_default=True)
    db.add(p)
    db.commit()
    return p


def _line(db, ent, name, kind, budget=None, actual=None):
    c = Category(name=name, kind=kind, entity_id=ent.id)
    db.add(c)
    db.commit()
    if budget is not None:
        db.add(Budget(category_id=c.id, entity_id=ent.id, monthly_limit=budget, year_month=YM))
    if actual is not None:
        db.add(ManualActual(category_id=c.id, entity_id=ent.id, year_month=YM, amount=actual))
    db.commit()


def test_nothing_entered_gives_no_fake_variance(db_session):
    p = _setup(db_session)
    _line(db_session, p, "Mortgage", "expense", budget=3000)
    _line(db_session, p, "Groceries", "expense", budget=800)
    o = month_overview(db_session, YM)
    assert o.expense.budget == 3800 and o.expense.actual == 0
    assert o.expense.entered == 0 and o.expense.missing == 2
    assert o.expense.variance == 0          # was -3800 before: budget vs nothing
    assert o.expense.projected == 3800


def test_partly_entered_month(db_session):
    p = _setup(db_session)
    _line(db_session, p, "Salary", "income", budget=6000, actual=6000)
    _line(db_session, p, "Airbnb", "income", budget=1500)                # not in yet
    _line(db_session, p, "Mortgage", "expense", budget=3000, actual=3000)
    _line(db_session, p, "Groceries", "expense", budget=800, actual=950)
    _line(db_session, p, "Dining", "expense", budget=300)                # not in yet
    _line(db_session, p, "Gift", "expense", actual=100)                  # unbudgeted
    o = month_overview(db_session, YM)

    assert (o.expense.lines, o.expense.entered, o.expense.missing) == (4, 3, 1)
    assert o.expense.compared_budget == 3800 and o.expense.actual == 4050
    assert o.expense.variance == 250                    # over budget on what's entered
    assert o.expense.projected == 4350                  # 4050 entered + 300 Dining budget
    assert o.income.projected == 7500
    assert o.saved_so_far == 6000 - 4050
    assert o.saved_projected == 7500 - 4350
    assert o.savings_rate == round(1950 / 6000, 4)
    assert o.complete is False


def test_no_income_means_no_savings_rate(db_session):
    p = _setup(db_session)
    _line(db_session, p, "Rent", "expense", budget=100, actual=100)
    o = month_overview(db_session, YM)
    assert o.savings_rate is None and o.complete is True and o.saved_so_far == -100


def test_dashboard_reports_month_overview(client, db_session):
    _setup(db_session)
    body = client.get("/api/dashboard/summary").json()
    assert set(body["month"]) >= {"income", "expense", "saved_so_far", "saved_projected", "savings_rate"}


def test_month_overview_endpoint(client, db_session):
    p = _setup(db_session)
    _line(db_session, p, "Rent", "expense", budget=100, actual=120)
    body = client.get(f"/api/actuals/month-overview?year_month={YM}").json()
    assert body["expense"]["variance"] == 20 and body["saved_so_far"] == -120
    assert client.get("/api/actuals/month-overview?year_month=bad").status_code == 422
