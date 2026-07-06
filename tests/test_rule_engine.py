"""Tests for PR2: Rule engine integration with importer/Plaid, account→entity
one-click mapping, and AI parser entity exclusion."""

from datetime import date

import pytest

from app.models import Account, Entity, EntityRule, Transaction


# ---- helpers ----

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


# ---- Rule engine service unit tests ----

def test_apply_rules_to_fields_matches_rule(db_session):
    """apply_rules_to_fields returns (entity_id, 'rule') when a rule matches."""
    from app.services.rule_engine import apply_rules_to_fields

    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)

    rule = EntityRule(
        entity_id=airbnb.id, field="name", operator="contains", value="airbnb",
        priority=50, is_active=True,
    )
    db_session.add(rule)
    db_session.commit()

    entity_id, source = apply_rules_to_fields(db_session, {
        "name": "Airbnb Cleaning Fee",
        "merchant_name": None,
        "account_id": acct.id,
        "category_id": None,
    })
    assert entity_id == airbnb.id
    assert source == "rule"


def test_apply_rules_to_fields_defaults_when_no_match(db_session):
    """apply_rules_to_fields returns default entity when no rule matches."""
    from app.services.rule_engine import apply_rules_to_fields

    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)

    rule = EntityRule(
        entity_id=airbnb.id, field="name", operator="equals", value="airbnb only",
        priority=50, is_active=True,
    )
    db_session.add(rule)
    db_session.commit()

    entity_id, source = apply_rules_to_fields(db_session, {
        "name": "Coffee Shop",
        "merchant_name": None,
        "account_id": acct.id,
        "category_id": None,
    })
    assert entity_id == house.id
    assert source == "default"


def test_apply_rules_to_transaction_skips_assigned(db_session):
    """If txn already has entity_id, apply_rules_to_transaction is a no-op."""
    from app.services.rule_engine import apply_rules_to_transaction

    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)

    rule = EntityRule(
        entity_id=airbnb.id, field="name", operator="contains", value="airbnb",
        priority=50, is_active=True,
    )
    db_session.add(rule)
    db_session.flush()

    txn = Transaction(
        account_id=acct.id,
        entity_id=house.id,
        entity_source="manual",
        amount=100.0,
        date=date.today(),
        name="Airbnb Cleaning",
        txn_type="expense",
        review_status="confirmed",
        review_source="manual",
        dedup_hash=Transaction.compute_dedup_hash(date.today(), 100.0, "Airbnb Cleaning", acct.id),
    )
    db_session.add(txn)
    db_session.flush()

    apply_rules_to_transaction(db_session, txn)

    # Should still be house, not airbnb, because it was already assigned
    assert txn.entity_id == house.id
    assert txn.entity_source == "manual"


def test_apply_rules_to_transaction_assigns_on_import(db_session):
    """Unassigned txn gets entity from rule engine."""
    from app.services.rule_engine import apply_rules_to_transaction

    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session, name="Airbnb CC")

    rule = EntityRule(
        entity_id=airbnb.id, field="account_id", operator="equals", value=str(acct.id),
        priority=10, is_active=True,
    )
    db_session.add(rule)
    db_session.flush()

    txn = Transaction(
        account_id=acct.id,
        amount=50.0,
        date=date.today(),
        name="Something",
        txn_type="expense",
        review_status="confirmed",
        review_source="csv_import",
        dedup_hash=Transaction.compute_dedup_hash(date.today(), 50.0, "Something", acct.id),
    )
    db_session.add(txn)
    db_session.flush()

    apply_rules_to_transaction(db_session, txn)

    assert txn.entity_id == airbnb.id
    assert txn.entity_source == "rule"


def test_infer_txn_type(db_session):
    """Positive = expense, negative = income."""
    from app.services.rule_engine import infer_txn_type

    assert infer_txn_type(100.0) == "expense"
    assert infer_txn_type(-50.0) == "income"
    assert infer_txn_type(0.0) == "expense"


# ---- CSV import integration with rule engine ----

def test_csv_import_applies_entity_rules(db_session):
    """When a CSV is imported, transactions get entity assignments from rules."""
    from app.services.importer import import_csv

    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session, name="Airbnb CC")

    # Create account-level rule
    rule = EntityRule(
        entity_id=airbnb.id, field="account_id", operator="equals", value=str(acct.id),
        priority=10, is_active=True,
    )
    db_session.add(rule)
    db_session.commit()

    csv_content = b"date,amount,name\n2025-01-15,50.00,Cleaning Supplies\n2025-01-16,-200.00,Guest Payment"
    source = import_csv(db_session, csv_content, "test.csv", acct.id)

    assert source.status == "completed"
    assert source.record_count == 2

    txns = db_session.query(Transaction).filter(
        Transaction.import_source_id == source.id
    ).all()
    assert len(txns) == 2

    for txn in txns:
        assert txn.entity_id == airbnb.id
        assert txn.entity_source == "rule"

    # Check txn_type inference
    expense = [t for t in txns if t.amount == 50.0][0]
    income = [t for t in txns if t.amount == -200.0][0]
    assert expense.txn_type == "expense"
    assert income.txn_type == "income"


def test_csv_import_defaults_entity_when_no_rule(db_session):
    """When no rule matches, imported txns get the default entity."""
    from app.services.importer import import_csv

    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)
    db_session.commit()

    csv_content = b"date,amount,name\n2025-01-15,50.00,Groceries"
    source = import_csv(db_session, csv_content, "test.csv", acct.id)

    assert source.status == "completed"
    txn = db_session.query(Transaction).filter(
        Transaction.import_source_id == source.id
    ).first()
    assert txn.entity_id == house.id
    assert txn.entity_source == "default"


def test_csv_import_name_rule_applies(db_session):
    """Name-based rules work during import."""
    from app.services.importer import import_csv

    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)

    rule = EntityRule(
        entity_id=airbnb.id, field="name", operator="contains", value="airbnb",
        priority=50, is_active=True,
    )
    db_session.add(rule)
    db_session.commit()

    csv_content = b"date,amount,name\n2025-01-15,150.00,Airbnb Insurance\n2025-01-16,30.00,Coffee"
    source = import_csv(db_session, csv_content, "test.csv", acct.id)

    txns = db_session.query(Transaction).filter(
        Transaction.import_source_id == source.id
    ).order_by(Transaction.name).all()
    assert len(txns) == 2

    airbnb_txn = [t for t in txns if "Airbnb" in t.name][0]
    coffee_txn = [t for t in txns if "Coffee" in t.name][0]
    assert airbnb_txn.entity_id == airbnb.id
    assert airbnb_txn.entity_source == "rule"
    assert coffee_txn.entity_id == house.id
    assert coffee_txn.entity_source == "default"


# ---- Account → entity mapping (one-click) ----

def test_account_entity_mapping_via_api(client, db_session):
    """POST /api/accounts/{id}/entity creates an account_id rule."""
    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session, name="Airbnb Visa")
    db_session.commit()

    resp = client.post(
        f"/api/accounts/{acct.id}/entity",
        json={"entity_id": airbnb.id, "priority": 10},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["field"] == "account_id"
    assert data["operator"] == "equals"
    assert data["value"] == str(acct.id)
    assert data["entity_id"] == airbnb.id
    assert data["priority"] == 10

    # Verify rule exists in DB
    rule = db_session.query(EntityRule).filter(
        EntityRule.field == "account_id",
        EntityRule.value == str(acct.id),
    ).first()
    assert rule is not None
    assert rule.entity_id == airbnb.id


def test_account_entity_mapping_updates_existing(client, db_session):
    """If a rule already exists for this account, update it instead of creating a duplicate."""
    house, airbnb = _seed_entities(db_session)
    biz = Entity(name="Business", entity_type="business")
    db_session.add(biz)
    db_session.flush()
    acct = _make_account(db_session)
    db_session.commit()

    # First mapping → Airbnb
    resp1 = client.post(
        f"/api/accounts/{acct.id}/entity",
        json={"entity_id": airbnb.id},
    )
    assert resp1.status_code == 201

    # Second mapping → Business (should update, not duplicate)
    resp2 = client.post(
        f"/api/accounts/{acct.id}/entity",
        json={"entity_id": biz.id},
    )
    assert resp2.status_code == 201

    rules = db_session.query(EntityRule).filter(
        EntityRule.field == "account_id",
        EntityRule.value == str(acct.id),
    ).all()
    assert len(rules) == 1
    assert rules[0].entity_id == biz.id


def test_account_entity_mapping_404_bad_account(client, db_session):
    _seed_entities(db_session)
    db_session.commit()

    resp = client.post("/api/accounts/9999/entity", json={"entity_id": 1})
    assert resp.status_code == 404


def test_account_entity_mapping_404_bad_entity(client, db_session):
    _seed_entities(db_session)
    acct = _make_account(db_session)
    db_session.commit()

    resp = client.post(f"/api/accounts/{acct.id}/entity", json={"entity_id": 9999})
    assert resp.status_code == 404
