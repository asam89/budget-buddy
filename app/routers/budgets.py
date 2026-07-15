from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Budget, Category, User
from app.schemas import BudgetCreate, BudgetFillForward, BudgetOut, BudgetUpsert
from app.services.aggregation import is_valid_year_month
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


def _upsert_budget(db: Session, category_id: int, year_month: str, monthly_limit: float) -> Budget:
    """Create or update the active dated budget for (category, month)."""
    existing = (
        db.query(Budget)
        .filter(
            Budget.category_id == category_id,
            Budget.is_active == True,  # noqa: E712
            Budget.year_month == year_month,
        )
        .first()
    )
    if existing is not None:
        existing.monthly_limit = monthly_limit
        return existing
    budget = Budget(category_id=category_id, monthly_limit=monthly_limit, year_month=year_month)
    db.add(budget)
    return budget


@router.get("/", response_model=list[BudgetOut])
def list_budgets(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return db.query(Budget).filter(Budget.is_active == True).order_by(Budget.category_id).all()


@router.post("/upsert", response_model=BudgetOut)
def upsert_budget(
    data: BudgetUpsert,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Set a category's budget for a specific month (inline tile/breakdown edit)."""
    if not is_valid_year_month(data.year_month):
        raise HTTPException(status_code=422, detail="year_month must be 'YYYY-MM'")
    if db.query(Category).filter(Category.id == data.category_id).first() is None:
        raise HTTPException(status_code=404, detail="Category not found")
    budget = _upsert_budget(db, data.category_id, data.year_month, data.monthly_limit)
    db.commit()
    db.refresh(budget)
    return budget


@router.post("/fill-forward")
def fill_forward_budget(
    data: BudgetFillForward,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Copy a month's budget to the remaining months of that year (never past months)."""
    if not is_valid_year_month(data.from_year_month):
        raise HTTPException(status_code=422, detail="from_year_month must be 'YYYY-MM'")
    if db.query(Category).filter(Category.id == data.category_id).first() is None:
        raise HTTPException(status_code=404, detail="Category not found")
    year, start_month = int(data.from_year_month[:4]), int(data.from_year_month[5:7])
    updated = 0
    for month in range(start_month, 13):
        _upsert_budget(db, data.category_id, f"{year:04d}-{month:02d}", data.monthly_limit)
        updated += 1
    db.commit()
    return {"updated": updated}


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
