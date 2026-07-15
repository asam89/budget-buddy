"""One-time migration that empties and removes the legacy ``Other`` category.

Budget Buddy no longer has a catch-all category (see ``category_guard``). Older
databases may still hold an ``Other`` category with budgets, transactions, or
manual actuals attached. This module enumerates that data grouped for review,
reassigns each group to a real category the user picks, and deletes ``Other``
once it is empty. Reassignment only re-points rows — no amount is created or
dropped — so ledger totals are preserved.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Budget, Category, ManualActual, Transaction
from app.services.category_guard import RESERVED_OTHER_MESSAGE, is_reserved_other

logger = logging.getLogger(__name__)


class ReassignmentError(ValueError):
    """Raised when a reassignment request is invalid."""


@dataclass
class Group:
    key: str          # stable identifier used by the reassign call
    kind: str         # 'transaction' | 'budget' | 'manual_actual'
    label: str        # human label for the group
    count: int
    amount: float     # signed sum of the group's amounts


def find_other(db: Session) -> Optional[Category]:
    """Return the ``Other`` category (case-insensitive) if one exists."""
    return (
        db.query(Category)
        .filter(func.lower(Category.name) == "other")
        .first()
    )


def _transaction_groups(db: Session, cat_id: int) -> list[Group]:
    rows = db.query(Transaction).filter(Transaction.category_id == cat_id).all()
    buckets: dict[str, list[Transaction]] = {}
    for t in rows:
        key = (t.merchant_name or t.name or "(no name)").strip() or "(no name)"
        buckets.setdefault(key, []).append(t)
    groups = []
    for key, txns in sorted(buckets.items()):
        groups.append(Group(
            key=f"txn:{key}",
            kind="transaction",
            label=key,
            count=len(txns),
            amount=round(sum(t.amount for t in txns), 2),
        ))
    return groups


def other_summary(db: Session) -> dict:
    """Describe what currently sits in ``Other`` so the UI can offer reassignment."""
    other = find_other(db)
    if other is None:
        return {"exists": False, "category_id": None, "groups": [], "totals": {}}

    groups = _transaction_groups(db, other.id)

    budgets = db.query(Budget).filter(Budget.category_id == other.id).all()
    if budgets:
        groups.append(Group(
            key="budgets",
            kind="budget",
            label="Budget targets",
            count=len(budgets),
            amount=round(sum(b.monthly_limit for b in budgets), 2),
        ))

    actuals = db.query(ManualActual).filter(ManualActual.category_id == other.id).all()
    if actuals:
        groups.append(Group(
            key="manual_actuals",
            kind="manual_actual",
            label="Manual actuals",
            count=len(actuals),
            amount=round(sum(a.amount for a in actuals), 2),
        ))

    return {
        "exists": True,
        "category_id": other.id,
        "groups": [g.__dict__ for g in groups],
        "totals": {
            "transactions": db.query(Transaction).filter(Transaction.category_id == other.id).count(),
            "budgets": len(budgets),
            "manual_actuals": len(actuals),
            "reference_amount": reference_total(db, other.id),
        },
    }


def reference_total(db: Session, cat_id: int) -> float:
    """Signed sum of every amount attached to a category (reconciliation check)."""
    txn = db.query(func.coalesce(func.sum(Transaction.amount), 0.0)).filter(
        Transaction.category_id == cat_id).scalar() or 0.0
    bud = db.query(func.coalesce(func.sum(Budget.monthly_limit), 0.0)).filter(
        Budget.category_id == cat_id).scalar() or 0.0
    man = db.query(func.coalesce(func.sum(ManualActual.amount), 0.0)).filter(
        ManualActual.category_id == cat_id).scalar() or 0.0
    return round(txn + bud + man, 2)


def _resolve_target(db: Session, to_category_id: Optional[int],
                    new_category_name: Optional[str], kind: str) -> Category:
    if new_category_name:
        if is_reserved_other(new_category_name):
            raise ReassignmentError(RESERVED_OTHER_MESSAGE)
        name = new_category_name.strip()
        target = db.query(Category).filter(Category.name == name).first()
        if target is None:
            target = Category(name=name, kind=kind if kind in ("expense", "income") else "expense")
            db.add(target)
            db.flush()
        return target
    if to_category_id is not None:
        target = db.query(Category).filter(Category.id == to_category_id).first()
        if target is None:
            raise ReassignmentError(f"Target category {to_category_id} not found")
        if is_reserved_other(target.name):
            raise ReassignmentError(RESERVED_OTHER_MESSAGE)
        return target
    raise ReassignmentError("Provide either to_category_id or new_category_name")


def reassign(db: Session, assignments: list[dict]) -> dict:
    """Re-point groups of Other data to real categories.

    Each assignment: ``{"group_key": str, "to_category_id": int|None,
    "new_category_name": str|None}``. Amounts are preserved; colliding manual
    actuals / active budgets are merged by summing.
    """
    other = find_other(db)
    if other is None:
        raise ReassignmentError("No Other category to migrate")

    moved = 0
    for a in assignments:
        key = a.get("group_key")
        if not key:
            raise ReassignmentError("Each assignment needs a group_key")
        target = _resolve_target(
            db, a.get("to_category_id"), a.get("new_category_name"),
            kind="expense",
        )
        if target.id == other.id:
            raise ReassignmentError("Cannot reassign Other onto itself")

        if key.startswith("txn:"):
            label = key[len("txn:"):]
            txns = db.query(Transaction).filter(Transaction.category_id == other.id).all()
            for t in txns:
                bucket = (t.merchant_name or t.name or "(no name)").strip() or "(no name)"
                if bucket == label:
                    t.category_id = target.id
                    moved += 1
        elif key == "budgets":
            moved += _move_budgets(db, other.id, target.id)
        elif key == "manual_actuals":
            moved += _move_manual_actuals(db, other.id, target.id)
        else:
            raise ReassignmentError(f"Unknown group_key: {key}")

    db.flush()
    remaining = reference_count(db, other.id)
    deleted = False
    if remaining == 0:
        db.delete(other)
        deleted = True
    db.commit()
    return {"moved": moved, "other_deleted": deleted, "remaining_references": remaining}


def _move_budgets(db: Session, from_id: int, to_id: int) -> int:
    moved = 0
    for b in db.query(Budget).filter(Budget.category_id == from_id).all():
        existing = (
            db.query(Budget)
            .filter(
                Budget.category_id == to_id,
                Budget.year_month.is_(b.year_month) if b.year_month is None
                else Budget.year_month == b.year_month,
                Budget.is_active == True,  # noqa: E712
            )
            .first()
        )
        if existing and existing.id != b.id:
            existing.monthly_limit = round(existing.monthly_limit + b.monthly_limit, 2)
            db.delete(b)
        else:
            b.category_id = to_id
        moved += 1
    return moved


def _move_manual_actuals(db: Session, from_id: int, to_id: int) -> int:
    moved = 0
    for m in db.query(ManualActual).filter(ManualActual.category_id == from_id).all():
        existing = (
            db.query(ManualActual)
            .filter(
                ManualActual.category_id == to_id,
                ManualActual.year_month == m.year_month,
            )
            .first()
        )
        if existing and existing.id != m.id:
            existing.amount = round(existing.amount + m.amount, 2)
            db.delete(m)
        else:
            m.category_id = to_id
        moved += 1
    return moved


def reference_count(db: Session, cat_id: int) -> int:
    """Number of rows still pointing at a category."""
    return (
        db.query(Transaction).filter(Transaction.category_id == cat_id).count()
        + db.query(Budget).filter(Budget.category_id == cat_id).count()
        + db.query(ManualActual).filter(ManualActual.category_id == cat_id).count()
    )


def complete_migration(db: Session) -> dict:
    """Delete ``Other`` iff empty; error if it still holds data."""
    other = find_other(db)
    if other is None:
        return {"other_deleted": False, "already_absent": True}
    remaining = reference_count(db, other.id)
    if remaining > 0:
        raise ReassignmentError(
            f"Other still has {remaining} references; reassign them first"
        )
    db.delete(other)
    db.commit()
    return {"other_deleted": True, "already_absent": False}


def silent_delete_if_empty(db: Session) -> bool:
    """On startup: if an empty ``Other`` exists, remove it silently."""
    other = find_other(db)
    if other is None:
        return False
    if reference_count(db, other.id) > 0:
        return False
    db.delete(other)
    db.commit()
    logger.info("Removed empty legacy 'Other' category on startup")
    return True
