from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Entity, EntityRule, Transaction, TransactionSplit, User
from app.schemas import (
    EntityOut, EntityCreate, EntityUpdate,
    EntityRuleOut, EntityRuleCreate,
    RuleApplyPreview, RuleApplyResult,
    TransactionSplitOut, TransactionSplitsRequest,
    SavedViewOut, SavedViewCreate,
    TransactionBulkEntityAssign,
)
from app.models import SavedView
from app.services.rule_engine import match_rule
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/entities", tags=["entities"])


# ---- Entity CRUD ----

@router.get("/", response_model=list[EntityOut])
def list_entities(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Entity)
    if is_active is not None:
        query = query.filter(Entity.is_active == is_active)
    return query.order_by(Entity.name).all()


@router.get("/{entity_id}", response_model=EntityOut)
def get_entity(
    entity_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.post("/", response_model=EntityOut, status_code=201)
def create_entity(
    data: EntityCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    existing = db.query(Entity).filter(Entity.name == data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Entity with this name already exists")

    if data.is_default:
        db.query(Entity).filter(Entity.is_default == True).update({"is_default": False})

    entity = Entity(
        name=data.name,
        entity_type=data.entity_type,
        color=data.color,
        icon=data.icon,
        is_default=data.is_default,
        notes=data.notes,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


@router.put("/{entity_id}", response_model=EntityOut)
def update_entity(
    entity_id: int,
    data: EntityUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    if data.name is not None:
        dup = db.query(Entity).filter(Entity.name == data.name, Entity.id != entity_id).first()
        if dup:
            raise HTTPException(status_code=409, detail="Entity with this name already exists")
        entity.name = data.name
    if data.entity_type is not None:
        entity.entity_type = data.entity_type
    if data.color is not None:
        entity.color = data.color
    if data.icon is not None:
        entity.icon = data.icon
    if data.is_default is not None:
        if data.is_default:
            db.query(Entity).filter(Entity.is_default == True, Entity.id != entity_id).update({"is_default": False})
        entity.is_default = data.is_default
    if data.is_active is not None:
        entity.is_active = data.is_active
    if data.notes is not None:
        entity.notes = data.notes

    db.commit()
    db.refresh(entity)
    return entity


@router.delete("/{entity_id}", status_code=204)
def deactivate_entity(
    entity_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    if entity.is_default:
        raise HTTPException(status_code=400, detail="Cannot deactivate the default entity")
    entity.is_active = False
    db.commit()


# ---- Entity Rules CRUD ----

@router.get("/{entity_id}/rules", response_model=list[EntityRuleOut])
def list_entity_rules(
    entity_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return (
        db.query(EntityRule)
        .filter(EntityRule.entity_id == entity_id)
        .order_by(EntityRule.priority)
        .all()
    )


@router.post("/{entity_id}/rules", response_model=EntityRuleOut, status_code=201)
def create_entity_rule(
    entity_id: int,
    data: EntityRuleCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    rule = EntityRule(
        entity_id=entity_id,
        field=data.field,
        operator=data.operator,
        value=data.value,
        priority=data.priority,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{entity_id}/rules/{rule_id}", status_code=204)
def delete_entity_rule(
    entity_id: int,
    rule_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    rule = db.query(EntityRule).filter(
        EntityRule.id == rule_id, EntityRule.entity_id == entity_id
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()


# ---- Retroactive rule application ----

def _txn_fields(txn: Transaction) -> dict:
    return {
        "name": txn.name,
        "merchant_name": txn.merchant_name,
        "account_id": txn.account_id,
        "category_id": txn.category_id,
    }


@router.post("/{entity_id}/rules/apply", response_model=RuleApplyPreview)
def apply_rules_preview(
    entity_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Dry-run: show how many transactions would be reassigned."""
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    rules = (
        db.query(EntityRule)
        .filter(EntityRule.entity_id == entity_id, EntityRule.is_active == True)
        .order_by(EntityRule.priority)
        .all()
    )
    if not rules:
        return RuleApplyPreview(matched_count=0, sample_transactions=[])

    # Find transactions NOT already assigned to this entity (exclude split txns)
    candidates = (
        db.query(Transaction)
        .filter(Transaction.entity_id != entity_id)
        .all()
    )

    matched = []
    for txn in candidates:
        if txn.splits:
            continue
        fields = _txn_fields(txn)
        for rule in rules:
            if match_rule(rule, fields):
                matched.append(txn)
                break

    sample = [
        {"id": t.id, "name": t.name, "date": t.date.isoformat(), "amount": t.amount}
        for t in matched[:10]
    ]
    return RuleApplyPreview(matched_count=len(matched), sample_transactions=sample)


@router.post("/{entity_id}/rules/apply/commit", response_model=RuleApplyResult)
def apply_rules_commit(
    entity_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Commit: reassign matching transactions to this entity."""
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    rules = (
        db.query(EntityRule)
        .filter(EntityRule.entity_id == entity_id, EntityRule.is_active == True)
        .order_by(EntityRule.priority)
        .all()
    )
    if not rules:
        return RuleApplyResult(updated_count=0)

    candidates = (
        db.query(Transaction)
        .filter(Transaction.entity_id != entity_id)
        .all()
    )

    updated = 0
    for txn in candidates:
        if txn.splits:
            continue
        fields = _txn_fields(txn)
        for rule in rules:
            if match_rule(rule, fields):
                txn.entity_id = entity_id
                txn.entity_source = "rule"
                updated += 1
                break

    db.commit()
    return RuleApplyResult(updated_count=updated)


# ---- Saved Views CRUD ----

@router.get("/views/all", response_model=list[SavedViewOut])
def list_saved_views(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return db.query(SavedView).order_by(SavedView.name).all()


@router.post("/views", response_model=SavedViewOut, status_code=201)
def create_saved_view(
    data: SavedViewCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    existing = db.query(SavedView).filter(SavedView.name == data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="View with this name already exists")

    view = SavedView(name=data.name, config=data.config)
    db.add(view)
    db.commit()
    db.refresh(view)
    return view


@router.put("/views/{view_id}", response_model=SavedViewOut)
def update_saved_view(
    view_id: int,
    data: SavedViewCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    view = db.query(SavedView).filter(SavedView.id == view_id).first()
    if not view:
        raise HTTPException(status_code=404, detail="Saved view not found")
    view.name = data.name
    view.config = data.config
    db.commit()
    db.refresh(view)
    return view


@router.delete("/views/{view_id}", status_code=204)
def delete_saved_view(
    view_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    view = db.query(SavedView).filter(SavedView.id == view_id).first()
    if not view:
        raise HTTPException(status_code=404, detail="Saved view not found")
    db.delete(view)
    db.commit()
