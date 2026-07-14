from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, Entity, EntityRule, User
from app.schemas import AccountOut, AccountCreate, AccountEntityMapRequest, EntityRuleOut
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("/", response_model=list[AccountOut])
def list_accounts(
    account_type: Optional[str] = None,
    is_active: bool = True,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Account).filter(Account.is_active == is_active)
    if account_type:
        query = query.filter(Account.account_type == account_type)
    return query.order_by(Account.name).all()


@router.get("/{account_id}", response_model=AccountOut)
def get_account(
    account_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post("/", response_model=AccountOut, status_code=201)
def create_manual_account(
    data: AccountCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    account = Account(
        name=data.name,
        account_type=data.account_type,
        account_subtype=data.account_subtype,
        current_balance=data.current_balance,
        currency=data.currency,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/{account_id}", status_code=204)
def deactivate_account(
    account_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.is_active = False
    db.commit()


@router.post("/{account_id}/entity", response_model=EntityRuleOut, status_code=201)
def map_account_to_entity(
    account_id: int,
    data: AccountEntityMapRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """One-click: create an account_id→entity rule (e.g., 'everything on this
    Airbnb credit card goes to the Airbnb entity').
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    entity = db.query(Entity).filter(Entity.id == data.entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    existing = (
        db.query(EntityRule)
        .filter(
            EntityRule.field == "account_id",
            EntityRule.operator == "equals",
            EntityRule.value == str(account_id),
        )
        .first()
    )
    if existing:
        existing.entity_id = data.entity_id
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    rule = EntityRule(
        entity_id=data.entity_id,
        field="account_id",
        operator="equals",
        value=str(account_id),
        priority=data.priority,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule
