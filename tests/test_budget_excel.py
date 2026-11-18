"""Excel export/import of the Income and Expenses grid."""

import io

import pytest
from openpyxl import load_workbook

from app.models import Budget, Category, Entity, ManualActual


@pytest.fixture
def seeded(db_session):
    personal = Entity(name="Personal", entity_type="personal", is_default=True)
    realesam = Entity(name="Realesam", entity_type="business")
    db_session.add_all([personal, realesam])
    db_session.commit()
    airbnb = Category(name="Rental - Airbnb", kind="income", entity_id=realesam.id)
    t4 = Category(name="T4", kind="income", entity_id=None)
    rent = Category(name="Rent", kind="expense", entity_id=personal.id)
    db_session.add_all([airbnb, t4, rent])
    db_session.commit()
    db_session.add_all([
        Budget(category_id=airbnb.id, entity_id=realesam.id, monthly_limit=1500, year_month=None),
        ManualActual(category_id=airbnb.id, entity_id=realesam.id, year_month="2026-11", amount=1500),
        ManualActual(category_id=t4.id, entity_id=personal.id, year_month="2026-11", amount=4000),
        Budget(category_id=rent.id, entity_id=personal.id, monthly_limit=2000, year_month="2026-11"),
    ])
    db_session.commit()
    return {"personal": personal, "realesam": realesam, "airbnb": airbnb, "t4": t4, "rent": rent}


def _export(client, **params):
    r = client.get("/api/budget-excel/export", params={"year": 2026, **params})
    assert r.status_code == 200
    return load_workbook(io.BytesIO(r.content))


def _rows(ws):
    return {(r[0], r[2]): r for r in ws.iter_rows(min_row=2, values_only=True)}


def _upload(client, wb, step):
    buf = io.BytesIO()
    wb.save(buf)
    return client.post(f"/api/budget-excel/{step}",
                       files={"file": ("b.xlsx", buf.getvalue(), "application/octet-stream")})


def test_export_matches_each_business_view(client, seeded):
    wb = _export(client)
    assert wb.sheetnames == ["How to use", "Expected", "Actual"]
    expected, actual = _rows(wb["Expected"]), _rows(wb["Actual"])
    assert expected[("Rental - Airbnb", "Realesam")][3:15] == (1500.0,) * 12
    assert actual[("Rental - Airbnb", "Realesam")][13] == 1500
    assert ("Rental - Airbnb", "Personal") not in actual            # owned: one row only
    assert actual[("T4", "Personal")][13] == 4000                   # shared: a row per business
    assert actual[("T4", "Realesam")][13] is None
    assert expected[("Rent", "Personal")][1] == "Expense"


def test_export_can_be_limited_to_income(client, seeded):
    names = {k[0] for k in _rows(_export(client, kind="income")["Actual"])}
    assert names == {"Rental - Airbnb", "T4"}


def test_unchanged_file_imports_as_no_changes(client, seeded):
    body = _upload(client, _export(client), "preview").json()
    assert body["change_count"] == 0 and body["errors"] == [] and body["new_lines"] == []


def test_edit_preview_then_apply(client, seeded, db_session):
    wb = _export(client)
    for row in wb["Actual"].iter_rows(min_row=2):
        if row[0].value == "Rental - Airbnb":
            row[13].value = 1650            # Nov actual
            row[14].value = 1500            # Dec actual (was blank)
        if row[0].value == "T4" and row[2].value == "Realesam":
            row[13].value = 300
    for row in wb["Expected"].iter_rows(min_row=2):
        if row[0].value == "Rent":
            row[3].value = "$2,100.00"      # Jan expected, typed as text
            row[13].value = None            # blank never clears
    preview = _upload(client, wb, "preview").json()
    got = {(c["line"], c["business"], c["month"], c["field"]): (c["old"], c["new"]) for c in preview["changes"]}
    assert got == {
        ("Rental - Airbnb", "Realesam", "2026-11", "actual"): (1500, 1650),
        ("Rental - Airbnb", "Realesam", "2026-12", "actual"): (None, 1500),
        ("T4", "Realesam", "2026-11", "actual"): (None, 300),
        ("Rent", "Personal", "2026-01", "expected"): (None, 2100),
    }
    assert db_session.query(ManualActual).count() == 2   # preview wrote nothing

    result = _upload(client, wb, "apply").json()
    assert result["actual_written"] == 3 and result["expected_written"] == 1
    after = _rows(_export(client)["Actual"])
    assert after[("Rental - Airbnb", "Realesam")][13] == 1650
    assert after[("T4", "Personal")][13] == 4000 and after[("T4", "Realesam")][13] == 300
    assert _rows(_export(client)["Expected"])[("Rent", "Personal")][13] == 2000   # not cleared


def test_new_line_is_created_under_its_business(client, seeded, db_session):
    wb = _export(client)
    wb["Actual"].append(["Rental - Village Green", "Income", "Realesam"] + [None] * 10 + [2300, None])
    preview = _upload(client, wb, "preview").json()
    assert preview["new_lines"] == [{"line": "Rental - Village Green", "kind": "income",
                                     "business": "Realesam", "entity_id": seeded["realesam"].id}]
    assert _upload(client, wb, "apply").json()["lines_created"] == 1
    cat = db_session.query(Category).filter_by(name="Rental - Village Green").one()
    assert cat.entity_id == seeded["realesam"].id and cat.kind == "income"
    assert _rows(_export(client)["Actual"])[("Rental - Village Green", "Realesam")][13] == 2300


def test_bad_rows_are_reported_and_skipped(client, seeded):
    wb = _export(client)
    ws = wb["Actual"]
    ws.append(["Rental - Airbnb", "Income", "Personal"] + [5] * 12)     # wrong business
    ws.append(["Rent", "Expense", "Nobody"] + [5] * 12)                 # unknown business
    ws.append(["Mystery", "", "Personal"] + [5] * 12)                   # new line, no type
    ws.append(["Rent", "Expense", "Personal"] + ["abc"] + [None] * 11)  # duplicate row
    ws.append(["Utilities", "Expense", "Personal"] + [-5] + [None] * 11)
    body = _upload(client, wb, "preview").json()
    assert body["change_count"] == 0
    errs = " | ".join(body["errors"])
    assert "belongs to Realesam" in errs and "unknown business 'Nobody'" in errs
    assert "needs Type Income or Expense" in errs and "appears twice" in errs
    assert "negative" in errs


def test_rejects_files_that_are_not_an_export(client, seeded):
    r = client.post("/api/budget-excel/preview", files={"file": ("x.xlsx", b"not excel", "application/octet-stream")})
    assert r.status_code == 422 and "isn't an Excel" in r.json()["detail"]
    wb = _export(client)
    wb["Actual"]["D1"] = "January"
    r = _upload(client, wb, "preview")
    assert r.status_code == 422 and "header row" in r.json()["detail"]
    wb = _export(client)
    del wb["How to use"]
    assert "Year" in _upload(client, wb, "preview").json()["detail"]
