import hashlib
import io
import json

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import User, ImportSource, ImportTemplate, Entity, Category
from app.schemas import ImportSourceOut
from app.services.importer import import_csv, import_excel
from app.services.ai_parser import parse_statement_text, extract_text_from_pdf
from app.services.sheet_mapper import (
    detect_header_row, clean_dataframe, profile_columns,
    heuristic_mapping, header_signature, parse_with_mapping, commit_rows,
)
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


# ------------------------------------------------------------------
# Smart spreadsheet import (PR6)
# ------------------------------------------------------------------


class SheetAnalyzeResponse(BaseModel):
    columns: list[str]
    profiles: list[dict]
    mapping: dict
    preview: list[dict]
    header_sig: str
    template_match: Optional[dict] = None


@router.post("/sheet/analyze")
async def analyze_sheet(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Analyze an uploaded spreadsheet: detect headers, profile columns, propose mapping."""
    content = await file.read()
    ext = (file.filename or "").lower().rsplit(".", 1)[-1] if file.filename and "." in file.filename else ""

    try:
        if ext in ("xlsx", "xls"):
            xls = pd.ExcelFile(io.BytesIO(content))
            sheets = xls.sheet_names
            target = sheet_name if sheet_name in sheets else sheets[0]
            df_raw = pd.read_excel(io.BytesIO(content), sheet_name=target, header=None)
        elif ext in ("csv", "tsv"):
            sep = "\t" if ext == "tsv" else ","
            df_raw = pd.read_csv(io.BytesIO(content), header=None, sep=sep)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read file: {e}")

    return _analyze_dataframe(db, df_raw, ext, file.filename or "upload")


@router.post("/sheet/analyze-paste")
async def analyze_paste(
    text: str = Form(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Analyze pasted TSV data from Google Sheets / Excel clipboard."""
    if not text.strip():
        raise HTTPException(status_code=400, detail="No data pasted")

    df_raw = pd.read_csv(io.StringIO(text), header=None, sep="\t")
    return _analyze_dataframe(db, df_raw, "paste", "clipboard")


def _analyze_dataframe(db: Session, df_raw: pd.DataFrame, source_type: str, filename: str):
    header_row = detect_header_row(df_raw)
    if header_row > 0:
        df = df_raw.iloc[header_row + 1:].reset_index(drop=True)
        df.columns = [str(c).strip() for c in df_raw.iloc[header_row]]
    else:
        df = df_raw.copy()
        df.columns = [str(c).strip() for c in df_raw.iloc[0]]
        df = df.iloc[1:].reset_index(drop=True)

    df = clean_dataframe(df)
    profiles = profile_columns(df)
    sig = header_signature(df.columns.tolist())

    # Check for saved template
    template = db.query(ImportTemplate).filter(
        ImportTemplate.header_signature == sig
    ).first()

    if template:
        mapping = json.loads(template.mapping)
        template_info = {"id": template.id, "name": template.name}
    else:
        mapping = heuristic_mapping(profiles)
        template_info = None

    # Preview first 50 rows
    preview = []
    for _, row in df.head(50).iterrows():
        preview.append({str(k): (None if pd.isna(v) else v) for k, v in row.items()})

    # Get sheet names if multi-sheet
    result = {
        "columns": df.columns.tolist(),
        "profiles": profiles,
        "mapping": mapping,
        "preview": preview,
        "header_sig": sig,
        "template_match": template_info,
    }
    return result


@router.get("/sheet/sheets")
async def list_sheets(
    file: UploadFile = File(...),
    _user: User = Depends(get_current_user),
):
    """List sheet names in an uploaded workbook."""
    content = await file.read()
    try:
        xls = pd.ExcelFile(io.BytesIO(content))
        return {"sheets": xls.sheet_names}
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read file: {e}")


class SheetCommitRequest(BaseModel):
    mapping: dict
    account_id: int
    default_entity_id: Optional[int] = None
    entity_map: Optional[dict[str, int]] = None
    category_map: Optional[dict[str, int]] = None
    save_template: Optional[str] = None  # template name to save


@router.post("/sheet/commit")
async def commit_sheet(
    file: UploadFile = File(...),
    config: str = Form(...),
    sheet_name: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Commit analyzed sheet data using confirmed mapping."""
    try:
        req = SheetCommitRequest.model_validate_json(config)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid config: {e}")

    content = await file.read()
    ext = (file.filename or "").lower().rsplit(".", 1)[-1] if file.filename and "." in file.filename else ""

    try:
        if ext in ("xlsx", "xls"):
            xls = pd.ExcelFile(io.BytesIO(content))
            target = sheet_name if sheet_name in xls.sheet_names else xls.sheet_names[0]
            df_raw = pd.read_excel(io.BytesIO(content), sheet_name=target, header=None)
        elif ext in ("csv", "tsv"):
            sep = "\t" if ext == "tsv" else ","
            df_raw = pd.read_csv(io.BytesIO(content), header=None, sep=sep)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported: .{ext}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read: {e}")

    return _commit_dataframe(db, df_raw, req, file.filename or "upload", "sheet_upload")


@router.post("/sheet/commit-paste")
async def commit_paste(
    text: str = Form(...),
    config: str = Form(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Commit pasted data using confirmed mapping."""
    try:
        req = SheetCommitRequest.model_validate_json(config)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid config: {e}")

    df_raw = pd.read_csv(io.StringIO(text), header=None, sep="\t")
    return _commit_dataframe(db, df_raw, req, "clipboard", "sheet_paste")


def _commit_dataframe(
    db: Session,
    df_raw: pd.DataFrame,
    req: SheetCommitRequest,
    filename: str,
    source_type: str,
):
    header_row = detect_header_row(df_raw)
    if header_row > 0:
        df = df_raw.iloc[header_row + 1:].reset_index(drop=True)
        df.columns = [str(c).strip() for c in df_raw.iloc[header_row]]
    else:
        df = df_raw.copy()
        df.columns = [str(c).strip() for c in df_raw.iloc[0]]
        df = df.iloc[1:].reset_index(drop=True)

    df = clean_dataframe(df)

    # Create ImportSource
    source = ImportSource(
        source_type=source_type,
        filename=filename,
        status="processing",
    )
    db.add(source)
    db.flush()

    # Build entity/category maps (case-insensitive)
    entity_map = {}
    if req.entity_map:
        entity_map = {k.lower(): v for k, v in req.entity_map.items()}
    else:
        for e in db.query(Entity).all():
            entity_map[e.name.lower()] = e.id

    category_map = {}
    if req.category_map:
        category_map = {k.lower(): v for k, v in req.category_map.items()}
    else:
        for c in db.query(Category).all():
            category_map[c.name.lower()] = c.id

    rows = parse_with_mapping(df, req.mapping, req.account_id, req.default_entity_id)
    stats = commit_rows(db, rows, source, entity_map, category_map)

    # Save template if requested
    if req.save_template:
        sig = header_signature(df.columns.tolist())
        existing = db.query(ImportTemplate).filter(
            ImportTemplate.header_signature == sig
        ).first()
        if existing:
            existing.mapping = json.dumps(req.mapping)
            existing.name = req.save_template
        else:
            tmpl = ImportTemplate(
                name=req.save_template,
                header_signature=sig,
                mapping=json.dumps(req.mapping),
            )
            db.add(tmpl)
        db.commit()

    return {
        "import_source_id": source.id,
        "added": stats["added"],
        "skipped_dedup": stats["skipped_dedup"],
        "total_rows": stats["total"],
    }


# Templates CRUD

@router.get("/templates")
def list_templates(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    templates = db.query(ImportTemplate).order_by(ImportTemplate.created_at.desc()).all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "header_signature": t.header_signature,
            "mapping": json.loads(t.mapping),
            "created_at": str(t.created_at),
        }
        for t in templates
    ]


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    tmpl = db.query(ImportTemplate).filter(ImportTemplate.id == template_id).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(tmpl)
    db.commit()
