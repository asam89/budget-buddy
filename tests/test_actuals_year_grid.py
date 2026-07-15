"""Regression tests for the batched year grid (GET /api/actuals/?year=).

The endpoint used to issue ~4 queries per (category, month) cell, i.e. it grew
linearly with categories x 12 and could lock/time out the encrypted SQLite on a
realistic category set. ``year_grid`` batches it into a constant number of
queries; these tests pin both the correctness (parity with the per-cell path)
and the query-count budget so the N+1 can't silently return.
"""

from datetime import date

from sqlalchemy import event

from app.models import Account, Budget, Category, ManualActual, Transaction
from app.services.aggregation import budget_for, effective_actual, year_grid


def _seed(db, n_categories=25):
    acc = Account(name="Checking", account_type="depository", current_balance=0)
    db.add(acc)
    db.flush()
    cats = []
    for i in range(n_categories):
        kind = "income" if i % 5 == 0 else "expense"
        c = Category(name=f"Cat{i:02d}", kind=kind)
        db.add(c)
        db.flush()
        cats.append(c)
        # every-month budget for some, dated for others
        if i % 2 == 0:
            db.add(Budget(category_id=c.id, monthly_limit=100 + i, year_month=None))
        else:
            db.add(Budget(category_id=c.id, monthly_limit=200 + i, year_month="2026-03"))
        # a manual actual in Feb, and a confirmed transaction in Jan
        db.add(ManualActual(category_id=c.id, year_month="2026-02", amount=50 + i))
        amt = -(300 + i) if kind == "income" else (40 + i)
        db.add(Transaction(
            account_id=acc.id, category_id=c.id, date=date(2026, 1, 15),
            amount=amt, name="t", review_status="confirmed",
            txn_type="income" if kind == "income" else "expense",
        ))
    db.commit()
    return cats


def test_year_grid_matches_per_cell_path(db_session):
    _seed(db_session, n_categories=12)
    lines = year_grid(db_session, 2026)
    cats = {c.id: c for c in db_session.query(Category).all()}
    for line in lines:
        cat = cats[line["category_id"]]
        for cell in line["cells"]:
            ym = cell["year_month"]
            eff = effective_actual(db_session, cat, ym)
            assert cell["effective"] == eff.amount
            assert cell["source"] == eff.source
            assert cell["transaction_sum"] == eff.transaction_sum
            assert cell["manual_amount"] == eff.manual_amount
            assert cell["budget"] == budget_for(db_session, cat.id, ym)


def test_year_grid_query_count_is_constant(db_session):
    engine = db_session.get_bind()
    counter = {"n": 0}

    def _count(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _count)
    try:
        _seed(db_session, n_categories=40)
        counter["n"] = 0
        lines = year_grid(db_session, 2026)
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    assert len(lines) == 40
    # categories + transactions + manual actuals + budgets = a small constant,
    # independent of category count (was ~40*12*3 before batching).
    assert counter["n"] <= 6, f"expected constant query count, got {counter['n']}"


def test_year_grid_endpoint_ok(client):
    resp = client.get("/api/actuals/?year=2026")
    assert resp.status_code == 200
    body = resp.json()
    assert body["year"] == 2026
    assert isinstance(body["lines"], list)
