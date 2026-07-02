from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bill, User
from app.schemas import BillOut, BillCreate
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/bills", tags=["bills"])


@router.get("/", response_model=list[BillOut])
def list_bills(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return db.query(Bill).filter(Bill.is_active == True).order_by(Bill.next_due_date).all()


@router.post("/", response_model=BillOut, status_code=201)
def create_bill(
    data: BillCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    bill = Bill(
        name=data.name,
        amount=data.amount,
        currency=data.currency,
        category_id=data.category_id,
        frequency=data.frequency,
        due_day=data.due_day,
        next_due_date=data.next_due_date,
        notes=data.notes,
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return bill


@router.put("/{bill_id}", response_model=BillOut)
def update_bill(
    bill_id: int,
    data: BillCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    bill.name = data.name
    bill.amount = data.amount
    bill.currency = data.currency
    bill.category_id = data.category_id
    bill.frequency = data.frequency
    bill.due_day = data.due_day
    bill.next_due_date = data.next_due_date
    bill.notes = data.notes
    db.commit()
    db.refresh(bill)
    return bill


@router.delete("/{bill_id}", status_code=204)
def delete_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    bill.is_active = False
    db.commit()
