from datetime import date

import pytest

from app.models import Transaction, Account
from app.services.importer import import_csv


def _make_account(db):
    acct = Account(name="Test Chequing", account_type="checking", current_balance=1000.0)
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


def test_dedup_hash_deterministic():
    h1 = Transaction.compute_dedup_hash(date(2025, 7, 1), 42.50, "Coffee Shop", 1)
    h2 = Transaction.compute_dedup_hash(date(2025, 7, 1), 42.50, "Coffee Shop", 1)
    assert h1 == h2


def test_dedup_hash_different_for_different_amounts():
    h1 = Transaction.compute_dedup_hash(date(2025, 7, 1), 42.50, "Coffee Shop", 1)
    h2 = Transaction.compute_dedup_hash(date(2025, 7, 1), 43.00, "Coffee Shop", 1)
    assert h1 != h2


def test_dedup_hash_case_insensitive_name():
    h1 = Transaction.compute_dedup_hash(date(2025, 7, 1), 42.50, "Coffee Shop", 1)
    h2 = Transaction.compute_dedup_hash(date(2025, 7, 1), 42.50, "coffee shop", 1)
    assert h1 == h2


def test_dedup_hash_strips_whitespace():
    h1 = Transaction.compute_dedup_hash(date(2025, 7, 1), 42.50, "Coffee Shop", 1)
    h2 = Transaction.compute_dedup_hash(date(2025, 7, 1), 42.50, "  Coffee Shop  ", 1)
    assert h1 == h2


def test_csv_import_no_duplicates_on_reimport(db_session):
    acct = _make_account(db_session)

    csv_content = b"date,amount,name\n2025-07-01,42.50,Coffee Shop\n2025-07-02,15.00,Gas Station\n"

    result1 = import_csv(db_session, csv_content, "test.csv", acct.id)
    assert result1.status == "completed"
    assert result1.record_count == 2

    txn_count_after_first = db_session.query(Transaction).count()
    assert txn_count_after_first == 2

    result2 = import_csv(db_session, csv_content, "test.csv", acct.id)
    assert result2.status == "duplicate"

    txn_count_after_second = db_session.query(Transaction).count()
    assert txn_count_after_second == 2


def test_csv_import_different_files_not_blocked(db_session):
    acct = _make_account(db_session)

    csv1 = b"date,amount,name\n2025-07-01,42.50,Coffee Shop\n"
    csv2 = b"date,amount,name\n2025-07-03,99.00,Grocery Store\n"

    result1 = import_csv(db_session, csv1, "july_1.csv", acct.id)
    result2 = import_csv(db_session, csv2, "july_3.csv", acct.id)

    assert result1.record_count == 1
    assert result2.record_count == 1
    assert db_session.query(Transaction).count() == 2


def test_two_same_day_same_amount_different_name(db_session):
    acct = _make_account(db_session)

    csv_content = b"date,amount,name\n2025-07-01,5.00,Starbucks\n2025-07-01,5.00,Tim Hortons\n"

    result = import_csv(db_session, csv_content, "coffees.csv", acct.id)
    assert result.record_count == 2
    assert db_session.query(Transaction).count() == 2
