"""Tests for PR6: Smart spreadsheet import — sheet_mapper, analyze, commit, templates."""

import io
import json
from datetime import date, timedelta

import pandas as pd
import pytest

from app.models import Account, Category, Entity, ImportTemplate, Transaction
from app.services.sheet_mapper import (
    detect_header_row, clean_dataframe, profile_columns,
    heuristic_mapping, header_signature, parse_with_mapping,
)


def _seed(db):
    house = Entity(name="House", entity_type="household", is_default=True)
    airbnb = Entity(name="Airbnb", entity_type="rental", is_default=False)
    db.add_all([house, airbnb])
    db.flush()

    acct = Account(name="Chequing", account_type="checking", current_balance=5000)
    db.add(acct)
    db.flush()

    groceries = Category(name="Groceries", is_system=True)
    utilities = Category(name="Utilities", is_system=True)
    db.add_all([groceries, utilities])
    db.flush()

    return house, airbnb, acct, groceries, utilities


# ---- detect_header_row ----

def test_header_on_row_0():
    df = pd.DataFrame([
        ["Date", "Amount", "Description"],
        ["2026-01-01", 100, "Groceries"],
        ["2026-01-02", 50, "Gas"],
    ])
    assert detect_header_row(df) == 0


def test_header_on_row_2():
    df = pd.DataFrame([
        ["", "", ""],
        ["My Spreadsheet", "", ""],
        ["Date", "Amount", "Description"],
        ["2026-01-01", 100, "Groceries"],
    ])
    assert detect_header_row(df) == 2


# ---- clean_dataframe ----

def test_clean_removes_total_rows():
    df = pd.DataFrame({
        "Name": ["Groceries", "Gas", "Total", "Subtotal"],
        "Amount": [100, 50, 150, 150],
    })
    cleaned = clean_dataframe(df)
    assert len(cleaned) == 2
    assert "Total" not in cleaned["Name"].values


def test_clean_removes_empty_rows():
    df = pd.DataFrame({
        "Name": ["Groceries", None, "Gas"],
        "Amount": [100, None, 50],
    })
    cleaned = clean_dataframe(df)
    assert len(cleaned) == 2


# ---- profile_columns ----

def test_profile_detects_date_column():
    df = pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "Amount": [100, 200, 300],
        "Name": ["A", "B", "C"],
    })
    profiles = profile_columns(df)
    date_profile = next(p for p in profiles if p["column"] == "Date")
    assert date_profile["date_parse_rate"] > 0.8


def test_profile_detects_numeric_column():
    df = pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02"],
        "Amount": ["100.50", "-200.00"],
        "Name": ["A", "B"],
    })
    profiles = profile_columns(df)
    amt_profile = next(p for p in profiles if p["column"] == "Amount")
    assert amt_profile["numeric_rate"] > 0.8


# ---- heuristic_mapping ----

def test_heuristic_mapping_basic():
    df = pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02"],
        "Amount": ["100", "200"],
        "Description": ["Groceries at store", "Gas station fill up"],
    })
    profiles = profile_columns(df)
    mapping = heuristic_mapping(profiles)
    assert mapping.get("date") == "Date"
    assert mapping.get("amount") == "Amount"
    assert mapping.get("name") == "Description"
    assert mapping["confidence"] == "low"


def test_heuristic_mapping_debit_credit():
    df = pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02"],
        "Debit": ["100", ""],
        "Credit": ["", "200"],
        "Description": ["Bought food", "Got paid"],
    })
    profiles = profile_columns(df)
    mapping = heuristic_mapping(profiles)
    assert "debit" in mapping
    assert "credit" in mapping


# ---- header_signature ----

def test_header_signature_consistent():
    sig1 = header_signature(["Date", "Amount", "Name"])
    sig2 = header_signature(["Name", "Date", "Amount"])  # different order
    assert sig1 == sig2


def test_header_signature_different_headers():
    sig1 = header_signature(["Date", "Amount", "Name"])
    sig2 = header_signature(["Date", "Amount", "Description"])
    assert sig1 != sig2


# ---- parse_with_mapping ----

def test_parse_with_mapping_basic():
    df = pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02"],
        "Amount": [100, -50],
        "Description": ["Groceries", "Refund"],
    })
    mapping = {"date": "Date", "amount": "Amount", "name": "Description", "sign_convention": "standard"}
    rows = parse_with_mapping(df, mapping, account_id=1)
    assert len(rows) == 2
    assert rows[0]["amount"] == 100
    assert rows[0]["name"] == "Groceries"
    assert rows[1]["amount"] == -50


def test_parse_with_sign_flip():
    df = pd.DataFrame({
        "Date": ["2026-01-01"],
        "Amount": [100],
        "Name": ["Groceries"],
    })
    mapping = {"date": "Date", "amount": "Amount", "name": "Name", "sign_convention": "expenses_positive"}
    rows = parse_with_mapping(df, mapping, account_id=1)
    assert rows[0]["amount"] == -100  # flipped


def test_parse_with_debit_credit():
    df = pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02"],
        "Debit": [100, 0],
        "Credit": [0, 200],
        "Name": ["Purchase", "Payment"],
    })
    mapping = {
        "date": "Date", "debit": "Debit", "credit": "Credit",
        "name": "Name", "amount_mode": "debit_credit",
        "sign_convention": "standard",
    }
    rows = parse_with_mapping(df, mapping, account_id=1)
    assert len(rows) == 2
    assert rows[0]["amount"] == 100  # debit
    assert rows[1]["amount"] == -200  # credit


def test_parse_with_entity_column():
    df = pd.DataFrame({
        "Date": ["2026-01-01", "2026-01-02"],
        "Amount": [100, 200],
        "Name": ["Hydro", "Rent"],
        "Property": ["House", "Airbnb"],
    })
    mapping = {"date": "Date", "amount": "Amount", "name": "Name", "entity": "Property", "sign_convention": "standard"}
    rows = parse_with_mapping(df, mapping, account_id=1)
    assert rows[0]["entity_name"] == "House"
    assert rows[1]["entity_name"] == "Airbnb"


# ---- API integration tests ----

def test_analyze_paste(client, db_session):
    _seed(db_session)
    db_session.commit()

    tsv_data = "Date\tAmount\tDescription\n2026-01-01\t100\tGroceries\n2026-01-02\t50\tGas"
    resp = client.post("/api/import/sheet/analyze-paste", data={"text": tsv_data})
    assert resp.status_code == 200
    data = resp.json()
    assert "columns" in data
    assert "mapping" in data
    assert "preview" in data
    assert len(data["preview"]) == 2


def test_commit_paste(client, db_session):
    house, airbnb, acct, groceries, utilities = _seed(db_session)
    db_session.commit()

    tsv_data = "Date\tAmount\tDescription\n2026-01-01\t100\tGroceries\n2026-01-02\t50\tGas"
    config = json.dumps({
        "mapping": {
            "date": "Date",
            "amount": "Amount",
            "name": "Description",
            "sign_convention": "standard",
        },
        "account_id": acct.id,
        "default_entity_id": house.id,
    })

    resp = client.post(
        "/api/import/sheet/commit-paste",
        data={"text": tsv_data, "config": config},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["added"] == 2
    assert data["skipped_dedup"] == 0


def test_commit_paste_dedup(client, db_session):
    """Re-import should skip duplicates."""
    house, airbnb, acct, groceries, utilities = _seed(db_session)
    db_session.commit()

    tsv_data = "Date\tAmount\tDescription\n2026-01-01\t100\tGroceries\n2026-01-02\t50\tGas"
    config = json.dumps({
        "mapping": {
            "date": "Date",
            "amount": "Amount",
            "name": "Description",
            "sign_convention": "standard",
        },
        "account_id": acct.id,
        "default_entity_id": house.id,
    })

    # First import
    resp = client.post("/api/import/sheet/commit-paste", data={"text": tsv_data, "config": config})
    assert resp.json()["added"] == 2

    # Re-import — should skip all
    resp = client.post("/api/import/sheet/commit-paste", data={"text": tsv_data, "config": config})
    assert resp.json()["added"] == 0
    assert resp.json()["skipped_dedup"] == 2


def test_commit_paste_with_entity_column(client, db_session):
    house, airbnb, acct, groceries, utilities = _seed(db_session)
    db_session.commit()

    tsv_data = "Date\tAmount\tDescription\tProperty\n2026-01-01\t100\tHydro\tHouse\n2026-01-02\t200\tRent Income\tAirbnb"
    config = json.dumps({
        "mapping": {
            "date": "Date",
            "amount": "Amount",
            "name": "Description",
            "entity": "Property",
            "sign_convention": "standard",
        },
        "account_id": acct.id,
        "default_entity_id": house.id,
    })

    resp = client.post("/api/import/sheet/commit-paste", data={"text": tsv_data, "config": config})
    assert resp.status_code == 200
    assert resp.json()["added"] == 2

    # Verify entity assignment
    txns = db_session.query(Transaction).filter(
        Transaction.review_source == "sheet_import"
    ).all()
    by_name = {t.name: t for t in txns}
    assert by_name["Hydro"].entity_id == house.id
    assert by_name["Rent Income"].entity_id == airbnb.id


def test_commit_paste_saves_template(client, db_session):
    house, airbnb, acct, groceries, utilities = _seed(db_session)
    db_session.commit()

    tsv_data = "Date\tAmount\tDescription\n2026-06-01\t100\tTest"
    config = json.dumps({
        "mapping": {
            "date": "Date",
            "amount": "Amount",
            "name": "Description",
            "sign_convention": "standard",
        },
        "account_id": acct.id,
        "save_template": "My Monthly Sheet",
    })

    resp = client.post("/api/import/sheet/commit-paste", data={"text": tsv_data, "config": config})
    assert resp.status_code == 200

    # Check template was saved
    resp = client.get("/api/import/templates")
    assert resp.status_code == 200
    templates = resp.json()
    assert len(templates) == 1
    assert templates[0]["name"] == "My Monthly Sheet"


def test_template_reuse_on_analyze(client, db_session):
    house, airbnb, acct, groceries, utilities = _seed(db_session)
    db_session.commit()

    # Save a template first
    tsv_data = "Date\tAmount\tDescription\n2026-06-01\t100\tTest"
    config = json.dumps({
        "mapping": {
            "date": "Date",
            "amount": "Amount",
            "name": "Description",
            "sign_convention": "standard",
        },
        "account_id": acct.id,
        "save_template": "Monthly Sheet",
    })
    client.post("/api/import/sheet/commit-paste", data={"text": tsv_data, "config": config})

    # Analyze with same headers — should match template
    tsv_data2 = "Date\tAmount\tDescription\n2026-07-01\t200\tNew Data"
    resp = client.post("/api/import/sheet/analyze-paste", data={"text": tsv_data2})
    data = resp.json()
    assert data["template_match"] is not None
    assert data["template_match"]["name"] == "Monthly Sheet"
    assert data["mapping"]["date"] == "Date"


def test_analyze_header_not_row_0(client, db_session):
    """Header on row 2 with title rows above."""
    _seed(db_session)
    db_session.commit()

    # Simulating TSV with empty lines and title before header
    tsv_data = "\t\t\nMy Budget Sheet\t\t\nDate\tAmount\tDescription\n2026-01-01\t100\tGroceries"
    resp = client.post("/api/import/sheet/analyze-paste", data={"text": tsv_data})
    assert resp.status_code == 200
    data = resp.json()
    assert "Date" in data["columns"]
    assert len(data["preview"]) >= 1


def test_delete_template(client, db_session):
    _seed(db_session)
    db_session.commit()

    # Create template
    tsv_data = "Date\tAmount\tDescription\n2026-06-01\t100\tTest"
    config = json.dumps({
        "mapping": {"date": "Date", "amount": "Amount", "name": "Description", "sign_convention": "standard"},
        "account_id": 1,
        "save_template": "To Delete",
    })
    client.post("/api/import/sheet/commit-paste", data={"text": tsv_data, "config": config})

    templates = client.get("/api/import/templates").json()
    assert len(templates) == 1

    resp = client.delete(f"/api/import/templates/{templates[0]['id']}")
    assert resp.status_code == 204

    templates = client.get("/api/import/templates").json()
    assert len(templates) == 0
