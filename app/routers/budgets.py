from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Budget, User
from app.schemas import BudgetOut, BudgetCreate
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


@router.get("/", response_model=list[BudgetOut])
def list_budgets(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return db.query(Budget).filter(Budget.is_active == True).order_by(Budget.category_id).all()


@router.post("/", response_model=BudgetOut, status_code=201)
def create_budget(
    data: BudgetCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    budget = Budget(
        category_id=data.category_id,
        monthly_limit=data.monthly_limit,
        year_month=data.year_month,
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


@router.put("/{budget_id}", response_model=BudgetOut)
def update_budget(
    budget_id: int,
    data: BudgetCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    budget = db.query(Budget).filter(Budget.id == budget_id).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    budget.category_id = data.category_id
    budget.monthly_limit = data.monthly_limit
    budget.year_month = data.year_month
    db.commit()
    db.refresh(budget)
    return budget


@router.delete("/{budget_id}", status_code=204)
def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    budget = db.query(Budget).filter(Budget.id == budget_id).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    budget.is_active = False
    db.commit()
