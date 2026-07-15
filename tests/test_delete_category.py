"""Deleting an expense/income line (the '-' button on the editable grid)."""

from datetime import date

from app.models import Account, Budget, Category, ManualActual, Transaction


def _account(db):
    acc = Account(name="Checking", account_type="depository", current_balance=0.0)
    db.add(acc)
    db.flush()
    return acc


def test_delete_category_removes_budgets_and_actuals(client, db_session):
    cat = Category(name="Other", kind="expense")
    db_session.add(cat)
    db_session.flush()
    db_session.add(Budget(category_id=cat.id, monthly_limit=58188.03))
    db_session.add(ManualActual(category_id=cat.id, year_month="2026-07", amount=10.0))
    db_session.commit()
    cat_id = cat.id

    resp = client.delete(f"/api/categories/{cat_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] is True
    assert body["budgets_deleted"] == 1
    assert body["manual_actuals_deleted"] == 1

    assert db_session.query(Category).filter(Category.id == cat_id).first() is None
    assert db_session.query(Budget).filter(Budget.category_id == cat_id).count() == 0
    assert (
        db_session.query(ManualActual)
        .filter(ManualActual.category_id == cat_id)
        .count()
        == 0
    )


def test_delete_category_blocked_when_transactions_exist(client, db_session):
    acc = _account(db_session)
    cat = Category(name="Groceries", kind="expense")
    db_session.add(cat)
    db_session.flush()
    db_session.add(Transaction(
        account_id=acc.id, category_id=cat.id, amount=25.0,
        date=date(2026, 7, 1), name="Store", review_status="confirmed",
    ))
    db_session.commit()
    cat_id = cat.id

    resp = client.delete(f"/api/categories/{cat_id}")
    assert resp.status_code == 409
    assert "reassign" in resp.json()["detail"].lower()
    # nothing removed
    assert db_session.query(Category).filter(Category.id == cat_id).first() is not None


def test_delete_missing_category_404(client):
    resp = client.delete("/api/categories/999999")
    assert resp.status_code == 404


def test_rename_category(client, db_session):
    cat = Category(name="Grocers", kind="expense")
    db_session.add(cat)
    db_session.commit()
    resp = client.patch(f"/api/categories/{cat.id}", json={"name": "Groceries"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Groceries"


def test_rename_to_other_rejected(client, db_session):
    cat = Category(name="Misc", kind="expense")
    db_session.add(cat)
    db_session.commit()
    resp = client.patch(f"/api/categories/{cat.id}", json={"name": "Other"})
    assert resp.status_code == 422


def test_rename_to_existing_name_conflicts(client, db_session):
    a = Category(name="Gas", kind="expense")
    b = Category(name="Fuel", kind="expense")
    db_session.add_all([a, b])
    db_session.commit()
    resp = client.patch(f"/api/categories/{b.id}", json={"name": "Gas"})
    assert resp.status_code == 409


def test_change_category_kind(client, db_session):
    cat = Category(name="Bonus", kind="expense")
    db_session.add(cat)
    db_session.commit()
    resp = client.patch(f"/api/categories/{cat.id}", json={"kind": "income"})
    assert resp.status_code == 200
    assert resp.json()["kind"] == "income"


def test_delete_reparents_children(client, db_session):
    parent = Category(name="Housing", kind="expense")
    db_session.add(parent)
    db_session.flush()
    child = Category(name="Mortgage", kind="expense", parent_id=parent.id)
    db_session.add(child)
    db_session.commit()
    parent_id = parent.id
    child_id = child.id

    resp = client.delete(f"/api/categories/{parent_id}")
    assert resp.status_code == 200

    refreshed = db_session.query(Category).filter(Category.id == child_id).first()
    assert refreshed is not None
    assert refreshed.parent_id is None
