"""Regression guard: month_totals/year_summary must stay batched.

They used to fan out into a per-category, per-month N+1 (~1000 queries for a
full grid) which locked/timed out the encrypted SQLite and surfaced as a 502 on
the Income/Expenses page. They now read the batched ``year_grid``, so the query
count must stay bounded regardless of how many categories exist.
"""

from datetime import datetime

from sqlalchemy import event

from app.models import Budget, Category, ManualActual
from app.services.aggregation import month_totals, year_summary


def _seed_many_categories(db, n: int = 40):
    ym = f"{datetime.utcnow().year}-01"
    for i in range(n):
        kind = "income" if i % 5 == 0 else "expense"
        cat = Category(name=f"Cat {i:03d}", kind=kind)
        db.add(cat)
        db.flush()
        db.add(ManualActual(category_id=cat.id, year_month=ym, amount=100.0))
        db.add(Budget(category_id=cat.id, monthly_limit=120.0, year_month=None))
    db.commit()


def _count_queries(session, fn):
    count = {"n": 0}

    def _before(*_args, **_kwargs):
        count["n"] += 1

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", _before)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return count["n"]


def test_month_totals_query_count_is_bounded(db_session):
    _seed_many_categories(db_session, 40)
    ym = f"{datetime.utcnow().year}-01"
    n = _count_queries(db_session, lambda: month_totals(db_session, ym))
    assert n <= 10, f"month_totals ran {n} queries (N+1 regression)"


def test_year_summary_query_count_is_bounded(db_session):
    _seed_many_categories(db_session, 40)
    year = datetime.utcnow().year
    n = _count_queries(db_session, lambda: year_summary(db_session, year))
    assert n <= 10, f"year_summary ran {n} queries (N+1 regression)"
