"""Excel round trip for the Income/Expenses grid.

Export writes one workbook per year: an "Expected" sheet and an "Actual" sheet
(one row per line and business, Jan-Dec columns) plus a "How to use" sheet.
Import reads the same layout, plans every change against the current values,
and only writes when asked to apply. Blank cells are ignored (never cleared),
and a cell is only written when its value differs from what the grid shows, so
untouched transaction-based actuals stay transaction-based.

All values come from ``aggregation.year_grid`` so the workbook shows exactly
what the grid shows for each business.
"""

import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.models import Budget, Category, Entity, ManualActual
from app.services.aggregation import year_grid
from app.services.category_guard import is_reserved_other

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
HEADER = ["Line", "Type", "Business"] + MONTHS
SHEETS = {"Expected": "budget", "Actual": "effective"}
TYPE_LABELS = {"income": "Income", "expense": "Expense"}
MAX_CHANGES_SHOWN = 500


class WorkbookError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _rows(db: Session, year: int, kind: Optional[str]) -> list[dict]:
    """One row per (line, business): owned lines once, shared lines per business."""
    entities = db.query(Entity).filter(Entity.is_active == True).order_by(Entity.name).all()  # noqa: E712
    names = {e.id: e.name for e in entities}
    rows = []
    for ent in entities:
        for line in year_grid(db, year, ent.id):
            if kind and line["kind"] != kind:
                continue
            rows.append({"line": line["category_name"], "kind": line["kind"],
                         "business": names[ent.id], "shared": line["entity_id"] is None,
                         "cells": line["cells"]})
    rows.sort(key=lambda r: (r["kind"] != "income", r["line"].lower(), r["business"].lower()))
    return rows


def build_workbook(db: Session, year: int, kind: Optional[str] = None) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    rows = _rows(db, year, kind)
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="1F7A55")
    for sheet, key in SHEETS.items():
        ws = wb.create_sheet(sheet)
        ws.append(HEADER)
        for c in ws[1]:
            c.font, c.fill = head_font, head_fill
            c.alignment = Alignment(horizontal="center")
        for r in rows:
            values = [r["cells"][m][key] for m in range(12)]
            ws.append([r["line"], TYPE_LABELS[r["kind"]], r["business"]] + values)
        for row in ws.iter_rows(min_row=2, min_col=4, max_col=15):
            for c in row:
                c.number_format = "#,##0.00"
        ws.freeze_panes = "D2"
        ws.column_dimensions["A"].width = 38
        ws.column_dimensions["B"].width = 10
        ws.column_dimensions["C"].width = 16
        for i in range(4, 16):
            ws.column_dimensions[get_column_letter(i)].width = 11

    info = wb.create_sheet("How to use", 0)
    for line in (
        ["Budget Buddy export"],
        ["Year", year],
        ["Exported", datetime.now().strftime("%Y-%m-%d %H:%M")],
        [],
        ["Edit amounts on the Expected and Actual sheets, then import this file on the Income or Expenses page."],
        ["You'll see every change before anything is saved."],
        ["Blank cells are ignored: importing never clears a value. Clear values in the app instead."],
        ["Shared lines have one row per business; owned lines have one row, under their business."],
        ["A new line name creates a new line owned by the business in its row (Type: Income or Expense)."],
        ["Don't rename the sheets, the header row, or the Year cell above."],
    ):
        info.append(line)
    info["A1"].font = Font(bold=True, size=14)
    info.column_dimensions["A"].width = 100

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

@dataclass
class Change:
    line: str
    business: str
    month: str          # YYYY-MM
    field: str          # "expected" | "actual"
    old: Optional[float]
    new: float
    category_id: Optional[int]   # None for a line created by this import
    entity_id: int
    kind: str


@dataclass
class Plan:
    year: int
    changes: list[Change] = field(default_factory=list)
    new_lines: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "year": self.year,
            "change_count": len(self.changes),
            "changes": [
                {"line": c.line, "business": c.business, "month": c.month, "field": c.field,
                 "old": c.old, "new": c.new}
                for c in self.changes[:MAX_CHANGES_SHOWN]
            ],
            "new_lines": self.new_lines,
            "errors": self.errors,
        }


def _num(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    s = str(value).strip().replace("$", "").replace(",", "")
    if s in ("", "-", "—", "–"):
        return None
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    return round(float(s), 2)


def _read_year(wb) -> int:
    if "How to use" in wb.sheetnames:
        for row in wb["How to use"].iter_rows(max_row=10, values_only=True):
            if row and str(row[0]).strip().lower() == "year" and len(row) > 1:
                try:
                    return int(row[1])
                except (TypeError, ValueError):
                    break
    raise WorkbookError("Couldn't find the Year on the 'How to use' sheet. "
                        "Export a fresh file from Budget Buddy and edit that.")


def plan_import(db: Session, data: bytes) -> Plan:
    try:
        wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except Exception:
        raise WorkbookError("That isn't an Excel (.xlsx) file Budget Buddy can read.")
    missing = [s for s in SHEETS if s not in wb.sheetnames]
    if missing:
        raise WorkbookError(f"Missing sheet(s): {', '.join(missing)}. Export a fresh file and edit that.")
    year = _read_year(wb)
    plan = Plan(year=year)

    entities = {e.name.strip().lower(): e for e in db.query(Entity).filter(Entity.is_active == True).all()}  # noqa: E712
    categories = {c.name.strip().lower(): c for c in db.query(Category).all()}
    grids = {e.id: {l["category_id"]: l for l in year_grid(db, year, e.id)} for e in entities.values()}
    new_lines: dict[str, dict] = {}

    for sheet, key in SHEETS.items():
        fld = "expected" if key == "budget" else "actual"
        ws = wb[sheet]
        rows = ws.iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else "" for h in next(rows, [])]
        if header[:len(HEADER)] != HEADER:
            raise WorkbookError(f"The header row on '{sheet}' was changed. It must be: {', '.join(HEADER)}.")
        seen: set[tuple[str, str]] = set()
        for i, row in enumerate(rows, start=2):
            row = list(row) + [None] * (len(HEADER) - len(row))
            name = str(row[0]).strip() if row[0] is not None else ""
            if not name:
                continue
            where = f"{sheet} row {i}"
            biz = str(row[2] or "").strip()
            ent = entities.get(biz.lower())
            if ent is None:
                plan.errors.append(f"{where}: unknown business '{biz}'. Skipped.")
                continue
            if (name.lower(), ent.name.lower()) in seen:
                plan.errors.append(f"{where}: '{name}' / {ent.name} appears twice. Skipped the second row.")
                continue
            seen.add((name.lower(), ent.name.lower()))
            try:
                values = [_num(v) for v in row[3:15]]
            except ValueError:
                plan.errors.append(f"{where}: a month cell isn't a number. Skipped the row.")
                continue
            if any(v is not None and v < 0 for v in values):
                plan.errors.append(f"{where}: negative amounts aren't allowed. Skipped the row.")
                continue

            cat = categories.get(name.lower())
            if cat is None:
                kind = {"income": "income", "expense": "expense"}.get(str(row[1] or "").strip().lower())
                if kind is None:
                    plan.errors.append(f"{where}: new line '{name}' needs Type Income or Expense. Skipped.")
                    continue
                if is_reserved_other(name):
                    plan.errors.append(f"{where}: '{name}' is a reserved name. Skipped.")
                    continue
                existing = new_lines.get(name.lower())
                if existing and existing["business"] != ent.name:
                    plan.errors.append(f"{where}: new line '{name}' is listed under two businesses. Skipped.")
                    continue
                if not existing:
                    new_lines[name.lower()] = {"line": name, "kind": kind, "business": ent.name,
                                               "entity_id": ent.id}
                cells = [None] * 12
                cat_id = None
            else:
                kind = cat.kind
                if cat.entity_id is not None and cat.entity_id != ent.id:
                    owner = next((e.name for e in entities.values() if e.id == cat.entity_id), "another business")
                    plan.errors.append(f"{where}: '{cat.name}' belongs to {owner}, not {ent.name}. Skipped.")
                    continue
                line = grids[ent.id].get(cat.id)
                cells = [c[key] for c in line["cells"]] if line else [None] * 12
                cat_id = cat.id

            for m, new in enumerate(values):
                if new is None:
                    continue
                old = cells[m]
                if old is not None and abs(old - new) < 0.005:
                    continue
                plan.changes.append(Change(
                    line=cat.name if cat else name, business=ent.name, month=f"{year:04d}-{m + 1:02d}",
                    field=fld, old=old, new=new, category_id=cat_id, entity_id=ent.id, kind=kind))

    plan.new_lines = list(new_lines.values())
    return plan


def apply_plan(db: Session, plan: Plan) -> dict:
    """Write a plan. Creates new lines first, then budgets and manual actuals."""
    created: dict[str, int] = {}
    for nl in plan.new_lines:
        cat = Category(name=nl["line"], kind=nl["kind"], entity_id=nl["entity_id"])
        db.add(cat)
        db.flush()
        created[nl["line"].lower()] = cat.id
    written = {"expected": 0, "actual": 0}
    for c in plan.changes:
        cat_id = c.category_id or created[c.line.lower()]
        if c.field == "expected":
            row = db.query(Budget).filter(
                Budget.category_id == cat_id, Budget.is_active == True,  # noqa: E712
                Budget.year_month == c.month, Budget.entity_id == c.entity_id).first()
            if row is None:
                db.add(Budget(category_id=cat_id, monthly_limit=c.new, year_month=c.month,
                              entity_id=c.entity_id))
            else:
                row.monthly_limit = c.new
        else:
            row = db.query(ManualActual).filter(
                ManualActual.category_id == cat_id, ManualActual.year_month == c.month,
                ManualActual.entity_id == c.entity_id).first()
            if row is None:
                db.add(ManualActual(category_id=cat_id, year_month=c.month, amount=c.new,
                                    entity_id=c.entity_id))
            else:
                row.amount = c.new
                row.updated_at = datetime.utcnow()
        written[c.field] += 1
    db.commit()
    return {"lines_created": len(created), "expected_written": written["expected"],
            "actual_written": written["actual"]}
