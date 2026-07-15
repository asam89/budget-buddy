"""WS-D: expense insights API — deterministic findings + optional AI narrative."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.database import get_db
from app.models import User
from app.services.ai_parser import _get_llm_provider
from app.services.aggregation import is_valid_year_month
from app.services.insights import build_findings, generate_insights, get_cached
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/insights", tags=["insights"])


def _validate(year_month: str) -> None:
    if not is_valid_year_month(year_month):
        raise HTTPException(status_code=422, detail="year_month must be 'YYYY-MM'")


@router.get("/findings")
def get_findings(
    year_month: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Deterministic findings only — fast, never calls the LLM.

    Lets the Expenses page render insights context immediately; the narrative is
    requested separately so the initial render is never blocked on AI.
    """
    _validate(year_month)
    findings = build_findings(db, year_month)
    cached = get_cached(findings)
    return {"findings": findings, "has_cached_narrative": cached is not None}


@router.post("/generate")
async def generate(
    year_month: str,
    force: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Produce (or return cached) validated AI narrative over the findings."""
    _validate(year_month)
    provider = _get_llm_provider(db)
    # Provider call is blocking network I/O; keep it off the event loop.
    return await run_in_threadpool(generate_insights, db, provider, year_month, force)
