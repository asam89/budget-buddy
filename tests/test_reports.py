"""Tests for PR4: Reports endpoints — pivot, P&L, entity comparison."""

from datetime import date, timedelta

from app.models import Account, Category, Entity, Transaction, TransactionSplit


def _seed(db):
    house = Entity(name="House", entity_type="household", is_default=True)
    airbnb = Entity(name="Airbnb", entity_type="rental", is_default=False)
    db.add_all([house, airbnb])
    db.flush()

    acct = Account(name="Chequing", account_type="checking", current_balance=5000)
    db.add(acct)
    db.flush()

    groceries = Category(name="Groceries", is_system=True)
    rent_income = Category(name="Rent Income", is_system=True)
    utilities = Category(name="Utilities", is_system=True)
    db.add_all([groceries, rent_income, utilities])
    db.flush()

    return house, airbnb, acct, groceries, rent_income, utilities


def _txn(db, acct, entity, cat, amount, name, days_ago=0):
    d = date.today() - timedelta(days=days_ago)
    txn = Transaction(
        account_id=acct.id,
        entity_id=entity.id if entity else None,
        entity_source="manual",
        category_id=cat.id if cat else None,
        amount=amount,
        date=d,
        name=name,
        txn_type="income" if amount < 0 else "expense",
        review_status="confirmed",
        review_source="manual",
        dedup_hash=Transaction.compute_dedup_hash(d, amount, name, acct.id),
    )
    db.add(txn)
    db.flush()
    return txn


# ---- Category × Month pivot ----

def test_category_month_pivot_expenses(client, db_session):
    house, airbnb, acct, groceries, rent_income, utilities = _seed(db_session)
    _txn(db_session, acct, house, groceries, 100, "Food", days_ago=1)
    _txn(db_session, acct, house, utilities, 200, "Hydro", days_ago=1)
    _txn(db_session, acct, airbnb, utilities, 50, "Airbnb Hydro", days_ago=1)
    db_session.commit()

    resp = client.get("/api/reports/category-month?months=1&mode=expense")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["months"]) >= 1
    assert len(data["rows"]) >= 2  # Groceries and Utilities


def test_category_month_pivot_entity_filter(client, db_session):
    house, airbnb, acct, groceries, rent_income, utilities = _seed(db_session)
    _txn(db_session, acct, house, groceries, 100, "Food", days_ago=1)
    _txn(db_session, acct, airbnb, utilities, 50, "Airbnb Hydro", days_ago=1)
    db_session.commit()

    resp = client.get(
        f"/api/reports/category-month?months=1&mode=expense&entity_id={airbnb.id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == airbnb.id
    # Only Airbnb txns
    total = sum(r["total"] for r in data["rows"])
    assert total == 50.0


def test_category_month_pivot_income_mode(client, db_session):
    house, airbnb, acct, groceries, rent_income, utilities = _seed(db_session)
    _txn(db_session, acct, airbnb, rent_income, -2000, "Tenant Rent", days_ago=1)
    _txn(db_session, acct, house, groceries, 100, "Food", days_ago=1)
    db_session.commit()

    resp = client.get("/api/reports/category-month?months=1&mode=income")
    data = resp.json()
    assert data["mode"] == "income"
    total = sum(r["total"] for r in data["rows"])
    assert total == 2000.0


# ---- Entity P&L ----

def test_entity_pnl_basic(client, db_session):
    house, airbnb, acct, groceries, rent_income, utilities = _seed(db_session)
    _txn(db_session, acct, airbnb, rent_income, -2000, "Rent", days_ago=5)
    _txn(db_session, acct, airbnb, utilities, 300, "Hydro", days_ago=3)
    _txn(db_session, acct, airbnb, groceries, 50, "Supplies", days_ago=1)
    db_session.commit()

    resp = client.get(f"/api/reports/entity-pnl?entity_id={airbnb.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_name"] == "Airbnb"
    assert data["total_income"] == 2000.0
    assert data["total_expenses"] == 350.0
    assert data["net"] == 1650.0
    assert len(data["income"]) == 1
    assert len(data["expenses"]) == 2


def test_entity_pnl_404(client, db_session):
    _seed(db_session)
    db_session.commit()
    resp = client.get("/api/reports/entity-pnl?entity_id=9999")
    assert resp.status_code == 404


def test_entity_pnl_with_splits(client, db_session):
    house, airbnb, acct, groceries, rent_income, utilities = _seed(db_session)
    txn = _txn(db_session, acct, None, utilities, 200, "Shared Hydro", days_ago=2)
    txn.entity_id = None
    # Split: 140 House, 60 Airbnb
    s1 = TransactionSplit(
        transaction_id=txn.id, entity_id=house.id, amount=140, percent=70
    )
    s2 = TransactionSplit(
        transaction_id=txn.id, entity_id=airbnb.id, amount=60, percent=30
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    resp = client.get(f"/api/reports/entity-pnl?entity_id={airbnb.id}")
    data = resp.json()
    assert data["total_expenses"] == 60.0

    resp = client.get(f"/api/reports/entity-pnl?entity_id={house.id}")
    data = resp.json()
    assert data["total_expenses"] == 140.0


# ---- Entity comparison ----

def test_entity_comparison(client, db_session):
    house, airbnb, acct, groceries, rent_income, utilities = _seed(db_session)
    _txn(db_session, acct, house, groceries, 500, "House Expenses", days_ago=1)
    _txn(db_session, acct, airbnb, rent_income, -2000, "Rent", days_ago=1)
    _txn(db_session, acct, airbnb, utilities, 300, "Airbnb Expenses", days_ago=1)
    db_session.commit()

    resp = client.get("/api/reports/entity-comparison?months=1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entities"]) >= 2
    assert len(data["month_labels"]) >= 1

    by_name = {e["entity_name"]: e for e in data["entities"]}
    this_month = data["month_labels"][-1]

    house_net = by_name["House"]["months"][this_month]["net"]
    assert house_net == -500.0  # only expenses

    airbnb_ent = by_name["Airbnb"]["months"][this_month]
    assert airbnb_ent["income"] == 2000.0
    assert airbnb_ent["expenses"] == 300.0
    assert airbnb_ent["net"] == 1700.0


def test_entity_comparison_empty(client, db_session):
    _seed(db_session)
    db_session.commit()

    resp = client.get("/api/reports/entity-comparison?months=1")
    data = resp.json()
    assert len(data["entities"]) == 2  # House + Airbnb, but zeros
