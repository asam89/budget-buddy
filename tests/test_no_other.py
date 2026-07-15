"""WS-A: no catch-all 'Other' category — guard, seed, budget setup, migration."""

from datetime import date

import pytest

from app.models import Account, Budget, Category, ManualActual, Transaction
from app.routers.categories import DEFAULT_CATEGORIES
from app.services.budget_setup import (
    UncategorizedItemsError,
    _propose_heuristic,
    commit_budget,
)
from app.services.category_guard import is_reserved_other
from app.services.other_migration import (
    ReassignmentError,
    find_other,
    reassign,
    reference_count,
    reference_total,
    silent_delete_if_empty,
)


# ---- guard + seed ----

def test_reserved_other_detection():
    assert is_reserved_other("Other")
    assert is_reserved_other("other")
    assert is_reserved_other("  OTHER  ")
    assert not is_reserved_other("Others")
    assert not is_reserved_other("Groceries")
    assert not is_reserved_other(None)


def test_default_seed_has_no_other():
    assert not any(is_reserved_other(c) for c in DEFAULT_CATEGORIES)


def test_seed_defaults_endpoint_creates_no_other(client, db_session):
    client.post("/api/categories/seed-defaults")
    names = [c.name for c in db_session.query(Category).all()]
    assert names
    assert not any(is_reserved_other(n) for n in names)


# ---- API guard ----

@pytest.mark.parametrize("name", ["Other", "other", "  Other  ", "OTHER"])
def test_create_other_category_rejected(client, name):
    resp = client.post("/api/categories/", json={"name": name, "kind": "expense"})
    assert resp.status_code == 422
    assert "review queue" in resp.json()["detail"].lower()


def test_create_real_category_still_works(client):
    resp = client.post("/api/categories/", json={"name": "Groceries", "kind": "expense"})
    assert resp.status_code == 201


# ---- budget setup ----

def test_heuristic_never_defaults_to_other():
    items = [{"label": "Something odd", "amount": 100.0, "period_hint": "monthly"}]
    out = _propose_heuristic(items, ["Groceries", "Gas"])
    assert out[0]["category"] is None


def test_commit_budget_rejects_unassigned(db_session):
    items = [
        {"category": "Groceries", "monthly_amount": 100.0, "kind": "expense"},
        {"category": None, "label": "Mystery", "monthly_amount": 50.0, "kind": "expense"},
    ]
    with pytest.raises(UncategorizedItemsError) as exc:
        commit_budget(db_session, items)
    assert "Mystery" in str(exc.value)
    # atomic: nothing created, no Other
    assert db_session.query(Category).count() == 0


def test_commit_budget_rejects_reserved_other(db_session):
    items = [{"category": "Other", "monthly_amount": 100.0, "kind": "expense"}]
    with pytest.raises(UncategorizedItemsError):
        commit_budget(db_session, items)
    assert find_other(db_session) is None


def test_commit_budget_creates_real_categories(db_session):
    items = [{"category": "Groceries", "monthly_amount": 100.0, "kind": "expense"}]
    res = commit_budget(db_session, items)
    assert res["categories_created"] == 1
    assert find_other(db_session) is None


# ---- migration ----

def _seed_other_with_data(db):
    acc = Account(name="Checking", account_type="depository", current_balance=0.0)
    db.add(acc)
    other = Category(name="Other", kind="expense")
    db.add(other)
    db.flush()
    db.add(Transaction(
        account_id=acc.id, category_id=other.id, amount=25.0,
        date=date(2026, 7, 1), name="Corner Store", merchant_name="Corner Store",
        review_status="confirmed",
    ))
    db.add(Budget(category_id=other.id, monthly_limit=200.0))
    db.add(ManualActual(category_id=other.id, year_month="2026-07", amount=40.0))
    db.commit()
    return other


def test_reassign_preserves_totals_and_deletes_other(db_session):
    other = _seed_other_with_data(db_session)
    target = Category(name="Groceries", kind="expense")
    db_session.add(target)
    db_session.flush()

    original_total = reference_total(db_session, other.id)
    other_id = other.id

    res = reassign(db_session, [
        {"group_key": "txn:Corner Store", "to_category_id": target.id},
        {"group_key": "budgets", "to_category_id": target.id},
        {"group_key": "manual_actuals", "to_category_id": target.id},
    ])

    assert res["other_deleted"] is True
    assert find_other(db_session) is None
    assert reference_count(db_session, other_id) == 0
    # totals preserved on the target
    assert reference_total(db_session, target.id) == original_total


def test_reassign_can_create_new_category(db_session):
    other = _seed_other_with_data(db_session)
    reassign(db_session, [
        {"group_key": "txn:Corner Store", "new_category_name": "Convenience"},
        {"group_key": "budgets", "new_category_name": "Convenience"},
        {"group_key": "manual_actuals", "new_category_name": "Convenience"},
    ])
    conv = db_session.query(Category).filter(Category.name == "Convenience").first()
    assert conv is not None
    assert find_other(db_session) is None


def test_reassign_rejects_new_other(db_session):
    _seed_other_with_data(db_session)
    with pytest.raises(ReassignmentError):
        reassign(db_session, [
            {"group_key": "txn:Corner Store", "new_category_name": "Other"},
        ])


def test_silent_delete_removes_empty_other(db_session):
    other = Category(name="Other", kind="expense")
    db_session.add(other)
    db_session.commit()
    assert silent_delete_if_empty(db_session) is True
    assert find_other(db_session) is None


def test_silent_delete_keeps_nonempty_other(db_session):
    _seed_other_with_data(db_session)
    assert silent_delete_if_empty(db_session) is False
    assert find_other(db_session) is not None
