"""Excel export/import for the Income and Expenses grid (see services.budget_workbook)."""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.budget_workbook import WorkbookError, apply_plan, build_workbook, plan_import
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/budget-excel", tags=["budget-excel"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/export")
def export_budget(
    year: int,
    kind: Optional[str] = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if kind not in (None, "income", "expense"):
        raise HTTPException(status_code=422, detail="kind must be income or expense")
    if not 1900 <= year <= 2200:
        raise HTTPException(status_code=422, detail="year out of range")
    label = {"income": "income", "expense": "expenses", None: "budget"}[kind]
    return Response(
        build_workbook(db, year, kind),
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="budget-buddy-{label}-{year}.xlsx"'},
    )


async def _plan(db: Session, file: UploadFile):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 10 MB")
    try:
        return plan_import(db, data)
    except WorkbookError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/preview")
async def preview_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """What importing this file would change. Writes nothing."""
    return (await _plan(db, file)).summary()


@router.post("/apply")
async def apply_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Re-plan from the file and write it. Rows listed as errors are skipped."""
    plan = await _plan(db, file)
    return {**apply_plan(db, plan), "errors": plan.errors, "year": plan.year}
