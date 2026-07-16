"""Item 3: entity-scoped dashboard summary and entity-breakdown.

Proves totals/spending are filtered by the selected entity, that a transaction
split across entities is never double counted, and that the "All" view rolls up
every entity.
"""

from datetime import date, datetime

from app.models import (
    Account,
    Category,
    Entity,
    Transaction,
    TransactionSplit,
)


def _today() -> date:
    return datetime.utcnow().date()


def _seed(db):
    personal = Entity(name="Personal", entity_type="personal", is_default=True, color="#10b981")
    biz = Entity(name="Ignyte", entity_type="business", color="#3b82f6")
    acc = Account(name="Checking", account_type="depository", current_balance=0)
    groceries = Category(name="Groceries", kind="expense")
    db.add_all([personal, biz, acc, groceries])
    db.commit()
    return personal, biz, acc, groceries


def _expense(db, acc, cat, entity_id, amount):
    # expense amounts are positive under the dashboard sign convention
    t = Transaction(
        account_id=acc.id,
        entity_id=entity_id,
        category_id=cat.id,
        amount=amount,
        date=_today(),
        name="x",
        txn_type="expense",
        review_status="confirmed",
    )
    db.add(t)
    db.commit()
    return t


def test_summary_is_scoped_to_entity(client, db_session):
    personal, biz, acc, cat = _seed(db_session)
    _expense(db_session, acc, cat, personal.id, 100.0)
    _expense(db_session, acc, cat, biz.id, 40.0)

    all_view = client.get("/api/dashboard/summary?months=1").json()
    assert all_view["total_expenses"] == 140.0

    personal_view = client.get(f"/api/dashboard/summary?months=1&entity_id={personal.id}").json()
    assert personal_view["total_expenses"] == 100.0

    biz_view = client.get(f"/api/dashboard/summary?months=1&entity_id={biz.id}").json()
    assert biz_view["total_expenses"] == 40.0


def test_split_not_double_counted(client, db_session):
    """A $100 Personal expense with $30 allocated to Ignyte: Personal keeps its
    full $100, Ignyte gets exactly the $30 split, and All still totals $100."""
    personal, biz, acc, cat = _seed(db_session)
    t = _expense(db_session, acc, cat, personal.id, 100.0)
    db_session.add(TransactionSplit(transaction_id=t.id, entity_id=biz.id, amount=30.0))
    db_session.commit()

    all_view = client.get("/api/dashboard/summary?months=1").json()
    assert all_view["total_expenses"] == 100.0

    personal_view = client.get(f"/api/dashboard/summary?months=1&entity_id={personal.id}").json()
    assert personal_view["total_expenses"] == 100.0

    biz_view = client.get(f"/api/dashboard/summary?months=1&entity_id={biz.id}").json()
    assert biz_view["total_expenses"] == 30.0


def test_entity_breakdown_rolls_up_all(client, db_session):
    personal, biz, acc, cat = _seed(db_session)
    _expense(db_session, acc, cat, personal.id, 100.0)
    _expense(db_session, acc, cat, biz.id, 40.0)

    rows = client.get("/api/dashboard/entity-breakdown?months=1").json()
    by_name = {r["entity_name"]: r for r in rows}
    assert by_name["Personal"]["expenses"] == 100.0
    assert by_name["Ignyte"]["expenses"] == 40.0
    assert by_name["Personal"]["color"] == "#10b981"
