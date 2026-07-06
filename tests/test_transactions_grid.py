"""Tests for PR3: Transactions grid backend — inline edit, totals, bulk entity, saved views."""

from datetime import date

import pytest

from app.models import Account, Entity, EntityRule, Transaction, TransactionSplit, SavedView


def _seed_entities(db):
    house = Entity(name="House", entity_type="household", is_default=True)
    airbnb = Entity(name="Airbnb", entity_type="rental", is_default=False)
    db.add_all([house, airbnb])
    db.flush()
    return house, airbnb


def _make_account(db, name="Chequing"):
    acct = Account(name=name, account_type="checking", current_balance=5000.0)
    db.add(acct)
    db.flush()
    return acct


def _make_txn(db, acct, entity, amount, name, review_source="manual", **kw):
    txn = Transaction(
        account_id=acct.id,
        entity_id=entity.id if entity else None,
        entity_source=kw.pop("entity_source", "manual"),
        amount=amount,
        date=kw.pop("date", date.today()),
        name=name,
        txn_type="income" if amount < 0 else "expense",
        review_status=kw.pop("review_status", "confirmed"),
        review_source=review_source,
        dedup_hash=Transaction.compute_dedup_hash(
            kw.get("date", date.today()), amount, name, acct.id
        ),
        **kw,
    )
    db.add(txn)
    db.flush()
    return txn


# ---- Inline edit ----

def test_inline_edit_name(client, db_session):
    house, _ = _seed_entities(db_session)
    acct = _make_account(db_session)
    txn = _make_txn(db_session, acct, house, 100.0, "Old Name")
    db_session.commit()

    resp = client.patch(f"/api/transactions/{txn.id}", json={"name": "New Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_inline_edit_entity(client, db_session):
    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)
    txn = _make_txn(db_session, acct, house, 50.0, "Something")
    db_session.commit()

    resp = client.patch(
        f"/api/transactions/{txn.id}", json={"entity_id": airbnb.id}
    )
    assert resp.status_code == 200
    assert resp.json()["entity_id"] == airbnb.id
    assert resp.json()["entity_source"] == "manual"


def test_inline_edit_category(client, db_session):
    house, _ = _seed_entities(db_session)
    acct = _make_account(db_session)
    txn = _make_txn(db_session, acct, house, 30.0, "Groceries")
    db_session.commit()

    from app.models import Category
    cat = Category(name="Food", is_system=True)
    db_session.add(cat)
    db_session.flush()
    db_session.commit()

    resp = client.patch(
        f"/api/transactions/{txn.id}", json={"category_id": cat.id}
    )
    assert resp.status_code == 200
    assert resp.json()["category_id"] == cat.id


def test_inline_edit_amount_blocked_for_csv(client, db_session):
    """Amount cannot be edited on imported (non-manual) transactions."""
    house, _ = _seed_entities(db_session)
    acct = _make_account(db_session)
    txn = _make_txn(db_session, acct, house, 100.0, "CSV Txn", review_source="csv_import")
    db_session.commit()

    resp = client.patch(
        f"/api/transactions/{txn.id}", json={"amount": 200.0}
    )
    assert resp.status_code == 422


def test_inline_edit_amount_allowed_for_manual(client, db_session):
    house, _ = _seed_entities(db_session)
    acct = _make_account(db_session)
    txn = _make_txn(db_session, acct, house, 100.0, "Manual Txn", review_source="manual")
    db_session.commit()

    resp = client.patch(
        f"/api/transactions/{txn.id}", json={"amount": -50.0}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["amount"] == -50.0
    assert data["txn_type"] == "income"


def test_inline_edit_notes(client, db_session):
    house, _ = _seed_entities(db_session)
    acct = _make_account(db_session)
    txn = _make_txn(db_session, acct, house, 10.0, "Coffee")
    db_session.commit()

    resp = client.patch(
        f"/api/transactions/{txn.id}", json={"notes": "Morning coffee"}
    )
    assert resp.status_code == 200
    assert resp.json()["notes"] == "Morning coffee"


def test_inline_edit_404(client, db_session):
    _seed_entities(db_session)
    db_session.commit()
    resp = client.patch("/api/transactions/9999", json={"name": "x"})
    assert resp.status_code == 404


# ---- Totals endpoint ----

def test_totals_basic(client, db_session):
    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)
    _make_txn(db_session, acct, house, 100.0, "Expense A")
    _make_txn(db_session, acct, airbnb, -200.0, "Income B")
    _make_txn(db_session, acct, house, 50.0, "Expense C")
    db_session.commit()

    resp = client.get("/api/transactions/totals")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3
    assert data["expenses"] == 150.0
    assert data["income"] == -200.0
    assert data["sum"] == -50.0


def test_totals_with_entity_filter(client, db_session):
    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)
    _make_txn(db_session, acct, house, 100.0, "House Expense")
    _make_txn(db_session, acct, airbnb, 200.0, "Airbnb Expense")
    db_session.commit()

    resp = client.get(f"/api/transactions/totals?entity_id={airbnb.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["sum"] == 200.0


def test_totals_entity_subtotals(client, db_session):
    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)
    _make_txn(db_session, acct, house, 100.0, "A")
    _make_txn(db_session, acct, airbnb, 50.0, "B")
    db_session.commit()

    resp = client.get("/api/transactions/totals")
    data = resp.json()
    subtotals = data["entity_subtotals"]
    assert subtotals[str(house.id)] == 100.0
    assert subtotals[str(airbnb.id)] == 50.0


# ---- Saved views via API ----

def test_saved_views_crud(client, db_session):
    _seed_entities(db_session)
    db_session.commit()

    # Create
    resp = client.post(
        "/api/entities/views",
        json={"name": "My View", "config": '{"filters":{"txn_type":"income"}}'},
    )
    assert resp.status_code == 201
    view_id = resp.json()["id"]

    # List
    resp = client.get("/api/entities/views/all")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "My View"

    # Update
    resp = client.put(
        f"/api/entities/views/{view_id}",
        json={"name": "Updated View", "config": '{"filters":{}}'},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated View"

    # Delete
    resp = client.delete(f"/api/entities/views/{view_id}")
    assert resp.status_code == 204

    resp = client.get("/api/entities/views/all")
    assert len(resp.json()) == 0


# ---- Bulk entity assign ----

def test_bulk_entity_assign(client, db_session):
    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)
    t1 = _make_txn(db_session, acct, house, 100.0, "T1")
    t2 = _make_txn(db_session, acct, house, 200.0, "T2")
    db_session.commit()

    resp = client.post(
        "/api/transactions/bulk-entity",
        json={"transaction_ids": [t1.id, t2.id], "entity_id": airbnb.id},
    )
    assert resp.status_code == 200
    assert resp.json()["updated_count"] == 2

    db_session.expire_all()
    assert db_session.get(Transaction, t1.id).entity_id == airbnb.id
    assert db_session.get(Transaction, t2.id).entity_id == airbnb.id
