from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, Institution
from app.schemas import AccountOut, AccountCreate

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("/", response_model=list[AccountOut])
def list_accounts(
    account_type: str | None = None,
    is_active: bool = True,
    db: Session = Depends(get_db),
):
    query = db.query(Account).filter(Account.is_active == is_active)
    if account_type:
        query = query.filter(Account.account_type == account_type)
    return query.order_by(Account.name).all()


@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post("/", response_model=AccountOut, status_code=201)
def create_manual_account(data: AccountCreate, db: Session = Depends(get_db)):
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
def deactivate_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.is_active = False
    db.commit()
