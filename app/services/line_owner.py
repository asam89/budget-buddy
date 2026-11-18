"""Keep a line's amounts with the business that owns the line.

Budgets and manual actuals carry their own ``entity_id``, separate from the
line's (``categories.entity_id``). A line owned by one business only appears in
that business's grid, so an amount filed under any other business is invisible
and uneditable there, yet still counted in the "All" view. That happened when
legacy amounts were backfilled to the default business, and whenever a line was
moved to another business.

``move_line_amounts`` re-files such amounts under the owner. If the owner
already has an amount for the same month (same budget slot), the owner's value
wins and the other row is left untouched and logged: nothing is deleted or
overwritten. Shared lines (``entity_id IS NULL``) legitimately hold a value per
business and are never touched. Transactions are not touched either: their
business reflects who paid, not who owns the line.
"""

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)


def move_line_amounts(conn, category_id: int, owner_id: int | None) -> dict:
    """Re-file one line's budgets and manual actuals under ``owner_id``.

    ``conn`` is a SQLAlchemy Connection or Session; the caller commits.
    Returns counts of moved and conflicting (left in place) rows.
    """
    result = {"budgets_moved": 0, "actuals_moved": 0, "budget_conflicts": 0, "actual_conflicts": 0}
    if owner_id is None:
        return result
    params = {"cat": category_id, "owner": owner_id}

    result["actuals_moved"] = conn.execute(text(
        """
        UPDATE manual_actuals SET entity_id = :owner
        WHERE category_id = :cat
          AND (entity_id IS NULL OR entity_id != :owner)
          AND NOT EXISTS (
            SELECT 1 FROM manual_actuals o
            WHERE o.category_id = :cat AND o.entity_id = :owner
              AND o.year_month = manual_actuals.year_month)
          AND id = (
            SELECT MIN(d.id) FROM manual_actuals d
            WHERE d.category_id = :cat AND (d.entity_id IS NULL OR d.entity_id != :owner)
              AND d.year_month = manual_actuals.year_month)
        """
    ), params).rowcount

    result["budgets_moved"] = conn.execute(text(
        """
        UPDATE budgets SET entity_id = :owner
        WHERE category_id = :cat
          AND (entity_id IS NULL OR entity_id != :owner)
          AND NOT EXISTS (
            SELECT 1 FROM budgets o
            WHERE o.category_id = :cat AND o.entity_id = :owner
              AND o.year_month IS budgets.year_month)
          AND id = (
            SELECT MIN(d.id) FROM budgets d
            WHERE d.category_id = :cat AND (d.entity_id IS NULL OR d.entity_id != :owner)
              AND d.year_month IS budgets.year_month)
        """
    ), params).rowcount

    result["actual_conflicts"] = conn.execute(text(
        "SELECT COUNT(*) FROM manual_actuals WHERE category_id = :cat "
        "AND (entity_id IS NULL OR entity_id != :owner)"), params).scalar()
    result["budget_conflicts"] = conn.execute(text(
        "SELECT COUNT(*) FROM budgets WHERE category_id = :cat "
        "AND (entity_id IS NULL OR entity_id != :owner)"), params).scalar()
    if result["actual_conflicts"] or result["budget_conflicts"]:
        logger.warning(
            "Line %s: %s manual actual(s) and %s budget(s) belong to another business "
            "but the owner already has a value for that month; left in place",
            category_id, result["actual_conflicts"], result["budget_conflicts"],
        )
    return result


def realign_all_owned_lines(conn) -> dict:
    """Startup repair: run move_line_amounts for every line owned by a business."""
    totals = {"budgets_moved": 0, "actuals_moved": 0, "budget_conflicts": 0, "actual_conflicts": 0}
    rows = conn.execute(text(
        "SELECT id, entity_id FROM categories WHERE entity_id IS NOT NULL")).fetchall()
    for cat_id, owner_id in rows:
        for k, v in move_line_amounts(conn, cat_id, owner_id).items():
            totals[k] += v
    if totals["budgets_moved"] or totals["actuals_moved"]:
        logger.info("Re-filed %s budget(s) and %s manual actual(s) under their line's business",
                    totals["budgets_moved"], totals["actuals_moved"])
    return totals
