from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Category, User
from app.schemas import CategoryOut, CategoryCreate
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/categories", tags=["categories"])

DEFAULT_CATEGORIES = [
    "Groceries", "Dining", "Transportation", "Gas", "Housing", "Utilities",
    "Insurance", "Healthcare", "Entertainment", "Shopping", "Personal Care",
    "Education", "Subscriptions", "Travel", "Gifts", "Salary", "Freelance",
    "Investment Income", "Refund", "Transfer", "Other",
]


@router.post("/seed-defaults", response_model=list[CategoryOut])
def seed_defaults(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    created = []
    for name in DEFAULT_CATEGORIES:
        existing = db.query(Category).filter(Category.name == name).first()
        if not existing:
            cat = Category(name=name, is_system=True)
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
    existing = db.query(Category).filter(Category.name == data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Category already exists")

    cat = Category(
        name=data.name,
        parent_id=data.parent_id,
        icon=data.icon,
        color=data.color,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat
