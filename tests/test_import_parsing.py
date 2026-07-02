import pytest

from app.models import Transaction, Account
from app.services.importer import import_csv, import_excel


def _make_account(db):
    acct = Account(name="Test Account", account_type="checking", current_balance=0)
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


def test_csv_basic_import(db_session):
    acct = _make_account(db_session)

    csv = b"date,amount,name\n2025-06-15,25.00,Grocery Store\n2025-06-16,-1500.00,Salary Deposit\n"
    result = import_csv(db_session, csv, "basic.csv", acct.id)

    assert result.status == "completed"
    assert result.record_count == 2

    txns = db_session.query(Transaction).order_by(Transaction.date).all()
    assert len(txns) == 2
    assert txns[0].amount == 25.00
    assert txns[0].name == "Grocery Store"
    assert txns[1].amount == -1500.00


def test_csv_with_merchant_and_category(db_session):
    acct = _make_account(db_session)

    csv = b"date,amount,name,merchant,category\n2025-06-15,42.00,POS Purchase,Costco,Groceries\n"
    result = import_csv(db_session, csv, "with_merchant.csv", acct.id)

    assert result.status == "completed"
    txn = db_session.query(Transaction).first()
    assert txn.merchant_name == "Costco"


def test_csv_various_date_formats(db_session):
    acct = _make_account(db_session)

    csv = b"date,amount,name\n07/01/2025,10.00,Test MM/DD\n2025-07-02,20.00,Test ISO\n"
    result = import_csv(db_session, csv, "dates.csv", acct.id)

    assert result.status == "completed"
    assert result.record_count == 2


def test_csv_missing_required_columns(db_session):
    acct = _make_account(db_session)

    csv = b"foo,bar,baz\n1,2,3\n"
    result = import_csv(db_session, csv, "bad.csv", acct.id)

    assert result.status == "failed"
    assert "Could not detect required columns" in (result.error_message or "")


def test_csv_alternative_column_names(db_session):
    acct = _make_account(db_session)

    csv = b"transaction_date,transaction_amount,description\n2025-07-01,33.00,Uber Eats\n"
    result = import_csv(db_session, csv, "alt_cols.csv", acct.id)

    assert result.status == "completed"
    assert result.record_count == 1


def test_csv_confirmed_by_default(db_session):
    acct = _make_account(db_session)

    csv = b"date,amount,name\n2025-07-01,10.00,Test\n"
    import_csv(db_session, csv, "confirmed.csv", acct.id)

    txn = db_session.query(Transaction).first()
    assert txn.review_status == "confirmed"
    assert txn.review_source == "csv_import"


def test_excel_import(db_session):
    acct = _make_account(db_session)

    import io
    import pandas as pd

    df = pd.DataFrame({
        "date": ["2025-07-01", "2025-07-02"],
        "amount": [50.0, 75.0],
        "name": ["Store A", "Store B"],
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    content = buf.getvalue()

    result = import_excel(db_session, content, "test.xlsx", acct.id)

    assert result.status == "completed"
    assert result.record_count == 2
