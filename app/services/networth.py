"""Net worth aggregation — device-independent balance-sheet math.

Kept out of the router so it can be unit tested without HTTP. All amounts
are rounded to cents to avoid float drift in totals.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import (
    Asset, Liability, Entity, ASSET_CLASSES, LIABILITY_CLASSES,
)

ASSET_CLASS_LABELS = {
    "cash": "Cash",
    "investment": "Investments",
    "real_estate": "Real Estate",
    "business": "Business",
    "vehicle": "Vehicles",
    "other": "Other",
}

LIABILITY_CLASS_LABELS = {
    "mortgage": "Mortgages",
    "loan": "Loans",
    "credit_card": "Credit Cards",
    "line_of_credit": "Lines of Credit",
    "other": "Other",
}


def _r(value: float) -> float:
    return round(value, 2)


@dataclass
class NetWorth:
    total_assets: float
    total_liabilities: float
    net_worth: float
    assets_by_class: list[dict]
    liabilities_by_class: list[dict]
    by_entity: list[dict]


def _class_breakdown(rows, amount_attr, class_attr, ordering, labels) -> list[dict]:
    """Sum ``amount_attr`` grouped by ``class_attr``, emitting only non-empty
    classes in the canonical ``ordering``. Unknown class values are folded
    into 'other' so a bad enum never silently drops from the total."""
    totals: dict[str, float] = {}
    for row in rows:
        cls = getattr(row, class_attr)
        if cls not in labels:
            cls = "other"
        totals[cls] = totals.get(cls, 0.0) + getattr(row, amount_attr)
    return [
        {"key": cls, "label": labels[cls], "total": _r(totals[cls])}
        for cls in ordering
        if cls in totals
    ]


def compute_net_worth(db: Session) -> NetWorth:
    """Compute the full balance sheet from active assets and liabilities."""
    assets = db.query(Asset).filter(Asset.is_active == True).all()
    liabilities = db.query(Liability).filter(Liability.is_active == True).all()

    total_assets = _r(sum(a.value for a in assets))
    total_liabilities = _r(sum(l.balance for l in liabilities))

    assets_by_class = _class_breakdown(
        assets, "value", "asset_class", ASSET_CLASSES, ASSET_CLASS_LABELS
    )
    liabilities_by_class = _class_breakdown(
        liabilities, "balance", "liability_class", LIABILITY_CLASSES,
        LIABILITY_CLASS_LABELS,
    )

    by_entity = _entity_breakdown(db, assets, liabilities)

    return NetWorth(
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        net_worth=_r(total_assets - total_liabilities),
        assets_by_class=assets_by_class,
        liabilities_by_class=liabilities_by_class,
        by_entity=by_entity,
    )


def _entity_breakdown(db: Session, assets, liabilities) -> list[dict]:
    """Assets/liabilities/net grouped by entity. Items with no entity are
    grouped under a synthetic 'Unassigned' bucket (entity_id=None)."""
    entity_names = {e.id: e.name for e in db.query(Entity).all()}

    buckets: dict[int | None, dict] = {}

    def bucket(entity_id):
        if entity_id not in buckets:
            buckets[entity_id] = {
                "entity_id": entity_id,
                "entity_name": entity_names.get(entity_id, "Unassigned")
                if entity_id is not None else "Unassigned",
                "assets": 0.0,
                "liabilities": 0.0,
            }
        return buckets[entity_id]

    for a in assets:
        bucket(a.entity_id)["assets"] += a.value
    for l in liabilities:
        bucket(l.entity_id)["liabilities"] += l.balance

    result = []
    for b in buckets.values():
        assets_total = _r(b["assets"])
        liabilities_total = _r(b["liabilities"])
        result.append({
            "entity_id": b["entity_id"],
            "entity_name": b["entity_name"],
            "assets": assets_total,
            "liabilities": liabilities_total,
            "net": _r(assets_total - liabilities_total),
        })

    # Named entities first (alphabetical), Unassigned last.
    result.sort(key=lambda r: (r["entity_id"] is None, r["entity_name"].lower()))
    return result
