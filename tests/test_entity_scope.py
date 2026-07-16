"""Entity-scoped budgets, manual actuals, and transaction-derived actuals.

Covers the reconciliation math per entity (including split allocations),
isolation between entities, and the "All" (entity_id=None) unscoped view.
"""

from datetime import date

from app.models import (
    Account,
    Budget,
    Category,
    Entity,
    ManualActual,
    Transaction,
    TransactionSplit,
)
from app.services.aggregation import (
    budget_for,
    effective_actual,
    month_totals,
    transaction_sum,
    year_grid,
)


def _base(db):
    personal = Entity(name="Personal", entity_type="personal", is_default=True)
    biz = Entity(name="Ignyte", entity_type="business")
    acc = Account(name="Checking", account_type="depository", current_balance=0)
    groceries = Category(name="Groceries", kind="expense")
    db.add_all([personal, biz, acc, groceries])
    db.commit()
    return personal, biz, acc, groceries


def test_budget_is_isolated_per_entity(db_session):
    personal, biz, _, cat = _base(db_session)
    db_session.add(Budget(category_id=cat.id, monthly_limit=500, year_month=None, entity_id=personal.id))
    db_session.add(Budget(category_id=cat.id, monthly_limit=1200, year_month=None, entity_id=biz.id))
    db_session.commit()

    assert budget_for(db_session, cat.id, "2026-03", personal.id) == 500
    assert budget_for(db_session, cat.id, "2026-03", biz.id) == 1200
    # "All" view sees whichever active row matches first; scoping is the point.
    assert budget_for(db_session, cat.id, "2026-03", None) in (500, 1200)


def test_manual_actual_isolated_per_entity(db_session):
    personal, biz, _, cat = _base(db_session)
    db_session.add(ManualActual(category_id=cat.id, year_month="2026-02", amount=80, entity_id=personal.id))
    db_session.add(ManualActual(category_id=cat.id, year_month="2026-02", amount=999, entity_id=biz.id))
    db_session.commit()

    assert effective_actual(db_session, cat, "2026-02", personal.id).amount == 80
    assert effective_actual(db_session, cat, "2026-02", biz.id).amount == 999


def test_transaction_sum_scoped_by_entity(db_session):
    personal, biz, acc, cat = _base(db_session)
    db_session.add(Transaction(
        account_id=acc.id, category_id=cat.id, entity_id=personal.id,
        date=date(2026, 1, 10), amount=100, name="p", review_status="confirmed",
        txn_type="expense",
    ))
    db_session.add(Transaction(
        account_id=acc.id, category_id=cat.id, entity_id=biz.id,
        date=date(2026, 1, 12), amount=40, name="b", review_status="confirmed",
        txn_type="expense",
    ))
    db_session.commit()

    assert transaction_sum(db_session, cat, "2026-01", personal.id) == 100
    assert transaction_sum(db_session, cat, "2026-01", biz.id) == 40
    assert transaction_sum(db_session, cat, "2026-01", None) == 140


def test_split_allocation_attributed_to_entity(db_session):
    personal, biz, acc, cat = _base(db_session)
    # A $100 expense owned by Personal, split $30 to Ignyte.
    txn = Transaction(
        account_id=acc.id, category_id=cat.id, entity_id=personal.id,
        date=date(2026, 1, 20), amount=100, name="shared", review_status="confirmed",
        txn_type="expense",
    )
    db_session.add(txn)
    db_session.flush()
    db_session.add(TransactionSplit(transaction_id=txn.id, entity_id=biz.id, amount=30))
    db_session.commit()

    # Ignyte gets only its split allocation; Personal keeps its direct amount.
    assert transaction_sum(db_session, cat, "2026-01", biz.id) == 30
    assert transaction_sum(db_session, cat, "2026-01", personal.id) == 100


def test_manual_overrides_transactions_per_entity(db_session):
    personal, biz, acc, cat = _base(db_session)
    db_session.add(Transaction(
        account_id=acc.id, category_id=cat.id, entity_id=biz.id,
        date=date(2026, 1, 5), amount=40, name="b", review_status="confirmed",
        txn_type="expense",
    ))
    db_session.add(ManualActual(category_id=cat.id, year_month="2026-01", amount=250, entity_id=biz.id))
    db_session.commit()

    eff = effective_actual(db_session, cat, "2026-01", biz.id)
    assert eff.amount == 250
    assert eff.source == "manual"
    assert eff.transaction_sum == 40  # reference kept, never summed


def test_year_grid_scoped_by_entity(db_session):
    personal, biz, acc, cat = _base(db_session)
    db_session.add(Budget(category_id=cat.id, monthly_limit=500, year_month=None, entity_id=personal.id))
    db_session.add(ManualActual(category_id=cat.id, year_month="2026-02", amount=80, entity_id=biz.id))
    db_session.commit()

    p_line = next(l for l in year_grid(db_session, 2026, personal.id) if l["category_id"] == cat.id)
    b_line = next(l for l in year_grid(db_session, 2026, biz.id) if l["category_id"] == cat.id)

    p_feb = next(c for c in p_line["cells"] if c["year_month"] == "2026-02")
    b_feb = next(c for c in b_line["cells"] if c["year_month"] == "2026-02")

    assert p_feb["budget"] == 500 and p_feb["manual_amount"] is None
    assert b_feb["budget"] is None and b_feb["manual_amount"] == 80


def test_year_grid_matches_single_cell_scoped(db_session):
    personal, biz, acc, cat = _base(db_session)
    db_session.add(Budget(category_id=cat.id, monthly_limit=500, year_month=None, entity_id=personal.id))
    db_session.add(Transaction(
        account_id=acc.id, category_id=cat.id, entity_id=personal.id,
        date=date(2026, 1, 10), amount=120, name="p", review_status="confirmed",
        txn_type="expense",
    ))
    db_session.commit()

    line = next(l for l in year_grid(db_session, 2026, personal.id) if l["category_id"] == cat.id)
    for cell in line["cells"]:
        ym = cell["year_month"]
        eff = effective_actual(db_session, cat, ym, personal.id)
        assert cell["effective"] == eff.amount
        assert cell["transaction_sum"] == eff.transaction_sum
        assert cell["budget"] == budget_for(db_session, cat.id, ym, personal.id)


def test_month_totals_scoped_by_entity(db_session):
    personal, biz, acc, cat = _base(db_session)
    db_session.add(ManualActual(category_id=cat.id, year_month="2026-01", amount=200, entity_id=personal.id))
    db_session.add(ManualActual(category_id=cat.id, year_month="2026-01", amount=50, entity_id=biz.id))
    db_session.commit()

    assert month_totals(db_session, "2026-01", personal.id).expense_actual == 200
    assert month_totals(db_session, "2026-01", biz.id).expense_actual == 50
