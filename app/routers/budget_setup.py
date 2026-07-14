"""Budget Setup router — AI-assisted onboarding from a summary budget sheet."""

import io

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import User
from app.services.budget_setup import (
    commit_budget,
    parse_budget_dataframe,
    propose_budget,
)
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/budget-setup", tags=["budget-setup"])


class BudgetProposalItem(BaseModel):
    label: str
    source_amount: float
    period: str
    monthly_amount: float
    category: str
    kind: str
    confidence: float
    note: str


class BudgetProposalResponse(BaseModel):
    ai_used: bool
    assisting_model: Optional[str] = None
    existing_categories: list[str]
    items: list[BudgetProposalItem]


def _read_dataframe(content: bytes, filename: str) -> pd.DataFrame:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    try:
        if ext in ("xlsx", "xls"):
            return pd.read_excel(io.BytesIO(content), header=None)
        if ext in ("csv", "tsv"):
            sep = "\t" if ext == "tsv" else ","
            return pd.read_csv(io.BytesIO(content), header=None, sep=sep)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read file: {e}")
    raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")


@router.post("/analyze", response_model=BudgetProposalResponse)
async def analyze_budget(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Parse an uploaded budget sheet and propose categories + monthly amounts."""
    content = await file.read()
    df_raw = _read_dataframe(content, file.filename or "upload")
    items = parse_budget_dataframe(df_raw)
    if not items:
        raise HTTPException(
            status_code=422,
            detail="Could not find any budget line items (need a label column and an amount column).",
        )
    return propose_budget(db, items)


@router.post("/analyze-paste", response_model=BudgetProposalResponse)
async def analyze_budget_paste(
    text: str = Form(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Parse pasted TSV budget data (from Google Sheets / Excel) and propose."""
    if not text.strip():
        raise HTTPException(status_code=400, detail="No data pasted")
    try:
        df_raw = pd.read_csv(io.StringIO(text), header=None, sep="\t")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse pasted data: {e}")
    items = parse_budget_dataframe(df_raw)
    if not items:
        raise HTTPException(
            status_code=422,
            detail="Could not find any budget line items (need a label column and an amount column).",
        )
    return propose_budget(db, items)


class BudgetCommitItem(BaseModel):
    category: str
    monthly_amount: float
    kind: str = "expense"


class BudgetCommitRequest(BaseModel):
    items: list[BudgetCommitItem]


@router.post("/commit")
def commit_budget_setup(
    req: BudgetCommitRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Create categories + monthly budget targets from the reviewed items."""
    if not req.items:
        raise HTTPException(status_code=400, detail="No budget items to commit")
    return commit_budget(db, [item.model_dump() for item in req.items])
