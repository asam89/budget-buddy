"""Endpoints for the one-time legacy 'Other' category reassignment."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.other_migration import (
    ReassignmentError,
    complete_migration,
    other_summary,
    reassign,
)
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/migration", tags=["migration"])


class Assignment(BaseModel):
    group_key: str
    to_category_id: Optional[int] = None
    new_category_name: Optional[str] = None


class ReassignRequest(BaseModel):
    assignments: list[Assignment]


@router.get("/other")
def get_other(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Summarize what sits in the legacy 'Other' category, grouped for review."""
    return other_summary(db)


@router.post("/other/reassign")
def reassign_other(
    req: ReassignRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    try:
        return reassign(db, [a.model_dump() for a in req.assignments])
    except ReassignmentError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/other/complete")
def complete_other(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    try:
        return complete_migration(db)
    except ReassignmentError as e:
        raise HTTPException(status_code=422, detail=str(e))
