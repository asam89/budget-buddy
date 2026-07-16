from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bill, Budget, Category, Entity, ManualActual, Transaction, User
from app.schemas import CategoryOut, CategoryCreate, CategoryUpdate
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


def _require_entity(db: Session, entity_id: int) -> Entity:
    ent = db.query(Entity).filter(Entity.id == entity_id).first()
    if ent is None:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    return ent


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

    if data.entity_id is not None:
        _require_entity(db, data.entity_id)

    kind = data.kind if data.kind in ("expense", "income") else "expense"
    cat = Category(
        name=data.name,
        kind=kind,
        parent_id=data.parent_id,
        entity_id=data.entity_id,
        icon=data.icon,
        color=data.color,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Rename an expense/income line or change its kind (inline grid edit)."""
    cat = db.query(Category).filter(Category.id == category_id).first()
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found")

    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Name cannot be blank")
        if is_reserved_other(name):
            raise HTTPException(status_code=422, detail=RESERVED_OTHER_MESSAGE)
        clash = (
            db.query(Category)
            .filter(Category.name == name, Category.id != category_id)
            .first()
        )
        if clash is not None:
            raise HTTPException(status_code=409, detail="Category already exists")
        cat.name = name

    if data.kind is not None:
        if data.kind not in ("expense", "income"):
            raise HTTPException(status_code=422, detail="kind must be 'expense' or 'income'")
        cat.kind = data.kind

    # NULL is a meaningful value here ("Shared"), so only touch entity_id when the
    # client actually sent the field.
    if "entity_id" in data.model_fields_set:
        if data.entity_id is not None:
            _require_entity(db, data.entity_id)
        cat.entity_id = data.entity_id

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
