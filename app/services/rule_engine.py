"""Entity rule engine: match transactions to entities based on EntityRule definitions.

Used at import time (CSV/Excel/Plaid sync) and for retroactive rule application.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Entity, EntityRule, Transaction

logger = logging.getLogger(__name__)


def match_rule(rule: EntityRule, txn_fields: dict) -> bool:
    """Check if a single rule matches the given transaction fields.

    txn_fields keys: 'name', 'merchant_name', 'account_id', 'category_id'
    Values should be the raw values from the transaction (strings, ints, or None).
    """
    if rule.field == "account_id":
        txn_val = str(txn_fields.get("account_id", ""))
    elif rule.field == "category_id":
        cat_id = txn_fields.get("category_id")
        txn_val = str(cat_id) if cat_id is not None else ""
    elif rule.field == "name":
        txn_val = (txn_fields.get("name") or "").lower()
    elif rule.field == "merchant_name":
        txn_val = (txn_fields.get("merchant_name") or "").lower()
    else:
        return False

    match_val = rule.value.lower() if rule.field not in ("account_id", "category_id") else rule.value

    if rule.operator == "equals":
        return txn_val == match_val
    elif rule.operator == "contains":
        return match_val in txn_val
    elif rule.operator == "starts_with":
        return txn_val.startswith(match_val)
    return False


def apply_rules_to_fields(db: Session, txn_fields: dict) -> tuple[Optional[int], str]:
    """Given transaction fields, find the matching entity via rules.

    Returns (entity_id, entity_source) where entity_source is 'rule' or 'default'.
    If no rule matches, returns the default entity.
    """
    rules = (
        db.query(EntityRule)
        .filter(EntityRule.is_active == True)
        .order_by(EntityRule.priority)
        .all()
    )

    for rule in rules:
        if match_rule(rule, txn_fields):
            return rule.entity_id, "rule"

    # No rule matched — use default entity
    default = db.query(Entity).filter(Entity.is_default == True).first()
    if default:
        return default.id, "default"
    return None, "default"


def apply_rules_to_transaction(db: Session, txn: Transaction) -> None:
    """Apply entity rules to a Transaction object in-place.

    Only sets entity if the transaction doesn't already have one assigned
    and has no splits.
    """
    if txn.entity_id is not None or txn.splits:
        return

    fields = {
        "name": txn.name,
        "merchant_name": txn.merchant_name,
        "account_id": txn.account_id,
        "category_id": txn.category_id,
    }
    entity_id, source = apply_rules_to_fields(db, fields)
    txn.entity_id = entity_id
    txn.entity_source = source


def infer_txn_type(amount: float) -> str:
    """Infer transaction type from amount sign.

    Convention: positive = expense, negative = income (credit/deposit).
    This matches the Plaid convention where positive amounts are debits.
    """
    if amount < 0:
        return "income"
    return "expense"
