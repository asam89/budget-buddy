from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bill, Budget, Category, ManualActual, Transaction, User
from app.schemas import CategoryOut, CategoryCreate
from app.services.category_guard import RESERVED_OTHER_MESSAGE, is_reserved_other
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/categories", tags=["categories"])

DEFAULT_CATEGORIES = [
    "Groceries", "Dining", "Transportation", "Gas", "Housing", "Utilities",
    "Insurance", "Healthcare", "Entertainment", "Shopping", "Personal Care",
    "Education", "Subscriptions", "Travel", "Gifts", "Salary", "Freelance",
    "Investment Income", "Refund", "Transfer",
]

_INCOME_CATEGORY_NAMES = {"Salary", "Freelance", "Investment Income"}


@router.post("/seed-defaults", response_model=list[CategoryOut])
def seed_defaults(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    created = []
    for name in DEFAULT_CATEGORIES:
        existing = db.query(Category).filter(Category.name == name).first()
        if not existing:
            kind = "income" if name in _INCOME_CATEGORY_NAMES else "expense"
            cat = Category(name=name, kind=kind, is_system=True)
            db.add(cat)
            created.append(cat)
    db.commit()
    for c in created:
        db.refresh(c)
    return created


@router.get("/", response_model=list[CategoryOut])
def list_categories(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return db.query(Category).order_by(Category.name).all()


@router.post("/", response_model=CategoryOut, status_code=201)
def create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if is_reserved_other(data.name):
        raise HTTPException(status_code=422, detail=RESERVED_OTHER_MESSAGE)

    existing = db.query(Category).filter(Category.name == data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Category already exists")

    kind = data.kind if data.kind in ("expense", "income") else "expense"
    cat = Category(
        name=data.name,
        kind=kind,
        parent_id=data.parent_id,
        icon=data.icon,
        color=data.color,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/{category_id}", status_code=200)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Remove an expense/income line.

    Blocked when transactions still reference the category — those must be
    reassigned in Review first (Budget Buddy has no catch-all to sweep them
    into). Otherwise deletes the category's budgets and manual actuals,
    detaches bills, reparents children, and removes the row.
    """
    cat = db.query(Category).filter(Category.id == category_id).first()
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found")

    txn_count = (
        db.query(Transaction).filter(Transaction.category_id == category_id).count()
    )
    if txn_count:
        raise HTTPException(
            status_code=409,
            detail=(
                f'"{cat.name}" still has {txn_count} transaction(s). Reassign '
                "them to another category in Review before deleting it."
            ),
        )

    budgets_deleted = (
        db.query(Budget).filter(Budget.category_id == category_id).delete()
    )
    manual_deleted = (
        db.query(ManualActual)
        .filter(ManualActual.category_id == category_id)
        .delete()
    )
    db.query(Bill).filter(Bill.category_id == category_id).update(
        {Bill.category_id: None}
    )
    db.query(Category).filter(Category.parent_id == category_id).update(
        {Category.parent_id: None}
    )
    db.delete(cat)
    db.commit()
    return {
        "deleted": True,
        "budgets_deleted": budgets_deleted,
        "manual_actuals_deleted": manual_deleted,
    }
