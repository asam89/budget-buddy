import hashlib

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, ImportSource
from app.schemas import ImportSourceOut
from app.services.importer import import_csv, import_excel
from app.services.ai_parser import parse_statement_text, extract_text_from_pdf
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/import", tags=["import"])


@router.post("/csv", response_model=ImportSourceOut)
async def upload_csv(
    file: UploadFile = File(...),
    account_id: int = Form(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    source = import_csv(db, content, file.filename, account_id)

    if source.status == "duplicate":
        raise HTTPException(status_code=409, detail="This file has already been imported")
    return source


@router.post("/excel", response_model=ImportSourceOut)
async def upload_excel(
    file: UploadFile = File(...),
    account_id: int = Form(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="File must be an Excel file (.xlsx/.xls)")

    content = await file.read()
    source = import_excel(db, content, file.filename, account_id)

    if source.status == "duplicate":
        raise HTTPException(status_code=409, detail="This file has already been imported")
    return source


@router.post("/statement", response_model=ImportSourceOut)
async def upload_statement(
    file: UploadFile = File(...),
    account_id: int = Form(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await file.read()
    ext = file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""

    if ext == "pdf":
        text = extract_text_from_pdf(content)
        if not text.strip():
            raise HTTPException(
                status_code=422,
                detail="Could not extract text from PDF. It may be a scanned document — image OCR not yet supported.",
            )
    elif ext in ("csv",):
        return import_csv(db, content, file.filename, account_id)
    elif ext in ("xlsx", "xls"):
        return import_excel(db, content, file.filename, account_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

    source = parse_statement_text(db, text, file.filename, account_id)
    if source.status == "failed":
        raise HTTPException(status_code=500, detail=source.error_message or "Parsing failed")
    return source


@router.get("/history", response_model=list[ImportSourceOut])
def list_imports(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return (
        db.query(ImportSource)
        .order_by(ImportSource.created_at.desc())
        .limit(50)
        .all()
    )
