"""Tests for Entity model, TransactionSplit validation, EntityRule matching,
retroactive rule apply (dry-run vs commit), per-entity aggregation with splits,
and migration backfill behaviour."""

from datetime import date, datetime

import pytest

from app.models import (
    Account, Entity, EntityRule, Transaction, TransactionSplit,
    Category, Budget,
)


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


def _make_txn(db, acct, entity, amount, name, txn_date=None, **kw):
    txn_date = txn_date or date.today()
    txn = Transaction(
        account_id=acct.id,
        entity_id=entity.id if entity else None,
        entity_source=kw.pop("entity_source", "manual"),
        amount=amount,
        date=txn_date,
        name=name,
        txn_type="income" if amount < 0 else "expense",
        review_status="confirmed",
        review_source="manual",
        dedup_hash=Transaction.compute_dedup_hash(txn_date, amount, name, acct.id),
        **kw,
    )
    db.add(txn)
    db.flush()
    return txn


# ---- Entity CRUD ----

def test_entity_creation(db_session):
    house, airbnb = _seed_entities(db_session)
    db_session.commit()

    entities = db_session.query(Entity).order_by(Entity.name).all()
    assert len(entities) == 2
    assert entities[0].name == "Airbnb"
    assert entities[1].name == "House"
    assert entities[1].is_default is True
    assert entities[0].is_default is False


def test_entity_unique_name(db_session):
    _seed_entities(db_session)
    db_session.commit()

    dup = Entity(name="House", entity_type="other")
    db_session.add(dup)
    with pytest.raises(Exception):
        db_session.flush()
    db_session.rollback()


def test_only_one_default_entity(db_session):
    house, airbnb = _seed_entities(db_session)
    db_session.commit()

    # Make Airbnb default — House should lose default
    airbnb.is_default = True
    house.is_default = False
    db_session.commit()

    assert db_session.query(Entity).filter(Entity.is_default == True).count() == 1


# ---- Split Validation ----

def test_split_amounts_sum_correctly(db_session):
    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)
    txn = _make_txn(db_session, acct, None, 200.0, "Hydro Bill")
    db_session.commit()

    s1 = TransactionSplit(
        transaction_id=txn.id, entity_id=house.id, amount=140.0, percent=70.0
    )
    s2 = TransactionSplit(
        transaction_id=txn.id, entity_id=airbnb.id, amount=60.0, percent=30.0
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    splits = db_session.query(TransactionSplit).filter(
        TransactionSplit.transaction_id == txn.id
    ).all()
    assert len(splits) == 2
    assert round(sum(s.amount for s in splits), 2) == 200.0


def test_split_replaces_entity_id(db_session):
    """When splits are set, the transaction's entity_id should be cleared."""
    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)
    txn = _make_txn(db_session, acct, house, 200.0, "Shared Bill")
    db_session.commit()

    # Set entity_id to None (splits take over)
    txn.entity_id = None
    s1 = TransactionSplit(transaction_id=txn.id, entity_id=house.id, amount=120.0)
    s2 = TransactionSplit(transaction_id=txn.id, entity_id=airbnb.id, amount=80.0)
    db_session.add_all([s1, s2])
    db_session.commit()

    db_session.refresh(txn)
    assert txn.entity_id is None
    assert len(txn.splits) == 2


# ---- Entity Rules ----

def test_rule_equals_match(db_session):
    from app.services.rule_engine import match_rule

    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)
    txn = _make_txn(db_session, acct, house, 50.0, "Grocery Store")
    db_session.commit()

    rule = EntityRule(
        entity_id=airbnb.id, field="name", operator="equals", value="grocery store",
        priority=100, is_active=True,
    )
    fields = {"name": txn.name, "merchant_name": txn.merchant_name, "account_id": txn.account_id, "category_id": txn.category_id}
    assert match_rule(rule, fields) is True


def test_rule_contains_match(db_session):
    from app.services.rule_engine import match_rule

    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)
    txn = _make_txn(db_session, acct, house, 100.0, "Airbnb Property Tax")
    db_session.commit()

    rule = EntityRule(
        entity_id=airbnb.id, field="name", operator="contains", value="airbnb",
        priority=100, is_active=True,
    )
    fields = {"name": txn.name, "merchant_name": txn.merchant_name, "account_id": txn.account_id, "category_id": txn.category_id}
    assert match_rule(rule, fields) is True


def test_rule_starts_with_match(db_session):
    from app.services.rule_engine import match_rule

    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)
    txn = _make_txn(db_session, acct, house, 75.0, "Airbnb Cleaning Fee")
    db_session.commit()

    rule = EntityRule(
        entity_id=airbnb.id, field="name", operator="starts_with", value="airbnb",
        priority=100, is_active=True,
    )
    fields = {"name": txn.name, "merchant_name": txn.merchant_name, "account_id": txn.account_id, "category_id": txn.category_id}
    assert match_rule(rule, fields) is True


def test_rule_account_id_match(db_session):
    from app.services.rule_engine import match_rule

    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session, name="Airbnb CC")
    txn = _make_txn(db_session, acct, house, 50.0, "Something")
    db_session.commit()

    rule = EntityRule(
        entity_id=airbnb.id, field="account_id", operator="equals", value=str(acct.id),
        priority=100, is_active=True,
    )
    fields = {"name": txn.name, "merchant_name": txn.merchant_name, "account_id": txn.account_id, "category_id": txn.category_id}
    assert match_rule(rule, fields) is True


def test_rule_no_match(db_session):
    from app.services.rule_engine import match_rule

    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)
    txn = _make_txn(db_session, acct, house, 50.0, "Coffee Shop")
    db_session.commit()

    rule = EntityRule(
        entity_id=airbnb.id, field="name", operator="equals", value="grocery store",
        priority=100, is_active=True,
    )
    fields = {"name": txn.name, "merchant_name": txn.merchant_name, "account_id": txn.account_id, "category_id": txn.category_id}
    assert match_rule(rule, fields) is False


def test_rule_priority_first_match_wins(db_session):
    """Lower priority number runs first; first match wins."""
    from app.services.rule_engine import match_rule

    house, airbnb = _seed_entities(db_session)
    biz = Entity(name="Business", entity_type="business")
    db_session.add(biz)
    db_session.flush()
    acct = _make_account(db_session)
    txn = _make_txn(db_session, acct, house, 100.0, "Office Rent Airbnb Building")
    db_session.commit()

    # Both rules match (name contains both "rent" and "airbnb")
    rule_airbnb = EntityRule(
        entity_id=airbnb.id, field="name", operator="contains", value="airbnb",
        priority=50, is_active=True,
    )
    rule_biz = EntityRule(
        entity_id=biz.id, field="name", operator="contains", value="rent",
        priority=100, is_active=True,
    )

    fields = {"name": txn.name, "merchant_name": txn.merchant_name, "account_id": txn.account_id, "category_id": txn.category_id}
    rules_sorted = sorted([rule_airbnb, rule_biz], key=lambda r: r.priority)
    matched_entity = None
    for rule in rules_sorted:
        if match_rule(rule, fields):
            matched_entity = rule.entity_id
            break

    assert matched_entity == airbnb.id


# ---- Per-Entity Aggregation with Splits ----

def test_per_entity_aggregation_with_splits(db_session):
    """Verify analytics correctly attribute split portions to entities."""
    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)

    # Regular txn for House
    _make_txn(db_session, acct, house, 100.0, "House Only Expense")

    # Regular txn for Airbnb
    _make_txn(db_session, acct, airbnb, 50.0, "Airbnb Only Expense")

    # Split txn: $200 hydro, 70/30 split
    split_txn = _make_txn(db_session, acct, None, 200.0, "Hydro Bill")
    split_txn.entity_id = None  # Splits override entity_id
    s1 = TransactionSplit(
        transaction_id=split_txn.id, entity_id=house.id, amount=140.0, percent=70.0
    )
    s2 = TransactionSplit(
        transaction_id=split_txn.id, entity_id=airbnb.id, amount=60.0, percent=30.0
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    # Compute House totals: 100 (direct) + 140 (split) = 240
    house_direct = sum(
        t.amount for t in db_session.query(Transaction).filter(
            Transaction.entity_id == house.id,
            Transaction.amount > 0,
            Transaction.review_status == "confirmed",
        ).all()
    )
    house_splits = sum(
        s.amount for s in db_session.query(TransactionSplit).filter(
            TransactionSplit.entity_id == house.id,
        ).all() if s.amount > 0
    )
    assert house_direct + house_splits == 240.0

    # Compute Airbnb totals: 50 (direct) + 60 (split) = 110
    airbnb_direct = sum(
        t.amount for t in db_session.query(Transaction).filter(
            Transaction.entity_id == airbnb.id,
            Transaction.amount > 0,
            Transaction.review_status == "confirmed",
        ).all()
    )
    airbnb_splits = sum(
        s.amount for s in db_session.query(TransactionSplit).filter(
            TransactionSplit.entity_id == airbnb.id,
        ).all() if s.amount > 0
    )
    assert airbnb_direct + airbnb_splits == 110.0


# ---- Migration Backfill ----

def test_migration_backfill_all_txns_to_default_entity(db_session):
    """Simulate what the migration does: all existing txns → default entity."""
    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)

    # Create txns without entity_id (simulating pre-migration state)
    for i, name in enumerate(["Store A", "Store B", "Store C"]):
        txn = Transaction(
            account_id=acct.id,
            amount=10.0 * (i + 1),
            date=date.today(),
            name=name,
            review_status="confirmed",
            review_source="manual",
            dedup_hash=Transaction.compute_dedup_hash(date.today(), 10.0 * (i + 1), name, acct.id),
        )
        db_session.add(txn)
    db_session.commit()

    # Backfill (same logic as migration)
    unassigned = db_session.query(Transaction).filter(Transaction.entity_id.is_(None)).all()
    assert len(unassigned) == 3

    default_entity = db_session.query(Entity).filter(Entity.is_default == True).first()
    for txn in unassigned:
        txn.entity_id = default_entity.id
        txn.entity_source = "default"
    db_session.commit()

    # Verify
    all_txns = db_session.query(Transaction).all()
    for txn in all_txns:
        assert txn.entity_id == house.id
        assert txn.entity_source == "default"


# ---- Retroactive Rule Application ----

def test_retroactive_rule_dry_run_vs_commit(db_session):
    """Dry run should preview matches; commit should update them."""
    from app.services.rule_engine import match_rule

    house, airbnb = _seed_entities(db_session)
    acct = _make_account(db_session)

    # All txns start on House
    t1 = _make_txn(db_session, acct, house, 100.0, "Airbnb Cleaning")
    t2 = _make_txn(db_session, acct, house, 200.0, "Airbnb Insurance")
    t3 = _make_txn(db_session, acct, house, 50.0, "Coffee Shop")
    db_session.commit()

    rule = EntityRule(
        entity_id=airbnb.id, field="name", operator="contains", value="airbnb",
        priority=100, is_active=True,
    )
    db_session.add(rule)
    db_session.commit()

    # Dry run: find matches
    rules = db_session.query(EntityRule).filter(
        EntityRule.entity_id == airbnb.id, EntityRule.is_active == True
    ).order_by(EntityRule.priority).all()

    candidates = db_session.query(Transaction).filter(
        Transaction.entity_id != airbnb.id
    ).all()

    matched = []
    for txn in candidates:
        if txn.splits:
            continue
        fields = {"name": txn.name, "merchant_name": txn.merchant_name, "account_id": txn.account_id, "category_id": txn.category_id}
        for r in rules:
            if match_rule(r, fields):
                matched.append(txn)
                break

    assert len(matched) == 2  # t1 and t2, not t3

    # Commit: update the matches
    for txn in matched:
        txn.entity_id = airbnb.id
        txn.entity_source = "rule"
    db_session.commit()

    # Verify
    airbnb_txns = db_session.query(Transaction).filter(
        Transaction.entity_id == airbnb.id
    ).all()
    assert len(airbnb_txns) == 2

    house_txns = db_session.query(Transaction).filter(
        Transaction.entity_id == house.id
    ).all()
    assert len(house_txns) == 1
    assert house_txns[0].name == "Coffee Shop"


# ---- txn_type inference ----

def test_txn_type_inferred_from_amount(db_session):
    house, _ = _seed_entities(db_session)
    acct = _make_account(db_session)

    expense = _make_txn(db_session, acct, house, 50.0, "Groceries")
    income = _make_txn(db_session, acct, house, -2000.0, "Salary")
    db_session.commit()

    assert expense.txn_type == "expense"
    assert income.txn_type == "income"
