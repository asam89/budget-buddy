"""Everyday spending: quick add, receipt scan and storage, API tokens and the ingest inbox."""

import base64
import io
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.database import get_db
from app.main import app
from app.models import Category, Entity, ManualActual, Receipt, Transaction
from app.services.aggregation import month_overview


def _jpeg(color=(200, 50, 50), size=(2400, 1800)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


class FakeVision:
    def __init__(self, result=None, boom=False):
        self.result, self.boom, self.seen = result, boom, None

    def complete_json_image(self, prompt, image, media_type, max_tokens=1024):
        if self.boom:
            raise RuntimeError("model down")
        self.seen = (image, media_type)
        return self.result

    def complete_json(self, prompt, schema=None, max_tokens=4096):
        if self.boom:
            raise RuntimeError("model down")
        return self.result


@pytest.fixture
def books(db_session):
    personal = Entity(name="Personal", entity_type="personal", is_default=True)
    realesam = Entity(name="Realesam", entity_type="business")
    db_session.add_all([personal, realesam])
    db_session.commit()
    leisure = Category(name="Leisure & Misc", kind="expense")
    dining = Category(name="Dining", kind="expense")
    salary = Category(name="Salary", kind="income")
    db_session.add_all([leisure, dining, salary])
    db_session.commit()
    return {"personal": personal, "realesam": realesam, "leisure": leisure, "dining": dining, "salary": salary}


def _admin(db_session):
    from app.models import User
    u = db_session.query(User).first()
    u.is_admin = True
    db_session.commit()


# ---- quick add ----

def test_quick_add_lands_in_the_expenses_grid(client, db_session, books):
    today = date.today()
    r = client.post("/api/spending", json={"amount": 18.5, "description": "Movie tickets",
                                           "category_id": books["leisure"].id})
    assert r.status_code == 201
    body = r.json()
    assert body["review_status"] == "confirmed" and body["entity_id"] == books["personal"].id
    txn = db_session.get(Transaction, body["id"])
    assert txn.amount == 18.5 and txn.txn_type == "expense"
    from app.models import Account
    assert db_session.get(Account, txn.account_id).name == "Everyday spending"
    past = (today - timedelta(days=3)).isoformat()
    dated = client.post("/api/spending", json={"amount": 7, "description": "Snacks", "date": past}).json()
    assert dated["date"] == past
    o = month_overview(db_session, today.strftime("%Y-%m"))
    assert o.expense.actual == 18.5

    # two identical coffees are both kept
    for _ in range(2):
        assert client.post("/api/spending", json={"amount": 5, "description": "Coffee"}).status_code == 201
    assert db_session.query(Transaction).filter(Transaction.name == "Coffee").count() == 2


def test_quick_add_validation_and_new_category(client, db_session, books):
    assert "more than zero" in client.post("/api/spending", json={"amount": 0, "description": "x"}).json()["detail"]
    assert "what it was for" in client.post("/api/spending", json={"amount": 3, "description": " "}).json()["detail"]
    future = (date.today() + timedelta(days=10)).isoformat()
    assert "future" in client.post("/api/spending", json={"amount": 3, "description": "x", "date": future}).json()["detail"]
    assert "expense category" in client.post("/api/spending", json={"amount": 3, "description": "x", "category_id": books["salary"].id}).json()["detail"]
    r = client.post("/api/spending", json={"amount": 40, "description": "Bowling", "new_category": "Fun Money",
                                           "entity_id": books["realesam"].id})
    cat = db_session.query(Category).filter_by(name="Fun Money").one()
    assert cat.kind == "expense" and r.json()["category_id"] == cat.id and r.json()["entity_id"] == books["realesam"].id
    # reusing an existing name doesn't create a duplicate line
    client.post("/api/spending", json={"amount": 1, "description": "x", "new_category": "dining"})
    assert db_session.query(Category).filter(Category.name.ilike("dining")).count() == 1


def test_quick_add_warns_when_a_typed_actual_hides_transactions(client, db_session, books):
    ym = date.today().strftime("%Y-%m")
    db_session.add(ManualActual(category_id=books["leisure"].id, entity_id=books["personal"].id,
                                year_month=ym, amount=100))
    db_session.commit()
    r = client.post("/api/spending", json={"amount": 10, "description": "Arcade", "category_id": books["leisure"].id})
    assert r.json()["manual_actual_overrides"] is True


# ---- receipts ----

def test_receipt_scan_reads_details_and_saves_once(client, db_session, books):
    fake = FakeVision({"merchant": "Cineplex", "date": date.today().isoformat(), "total": "$31.07",
                       "tax": 3.57, "currency": "CAD", "category": "dining", "summary": "2 tickets"})
    photo = _jpeg()
    with patch("app.routers.spending._get_llm_provider", return_value=fake):
        r = client.post("/api/spending/receipt/scan", files={"file": ("r.jpg", photo, "image/jpeg")})
    d = r.json()
    assert d["merchant"] == "Cineplex" and d["total"] == 31.07 and d["category_id"] == books["dining"].id
    assert d["warnings"] == []
    img, mt = fake.seen
    assert mt == "image/jpeg" and max(Image.open(io.BytesIO(img)).size) == 1600   # downscaled

    save = client.post("/api/spending", json={"amount": d["total"], "description": "Movie night",
                                              "merchant": d["merchant"], "receipt_id": d["receipt_id"]})
    assert save.status_code == 201 and save.json()["receipt_id"] == d["receipt_id"]
    assert db_session.get(Transaction, save.json()["id"]).review_source == "receipt"

    # viewing the receipt returns the original file
    view = client.get(f"/api/spending/receipts/{d['receipt_id']}")
    assert view.status_code == 200 and view.content == photo and view.headers["content-type"] == "image/jpeg"

    # uploading the same photo again is recognised; saving it again doesn't duplicate
    with patch("app.routers.spending._get_llm_provider", return_value=fake):
        again = client.post("/api/spending/receipt/scan", files={"file": ("r.jpg", photo, "image/jpeg")}).json()
    assert again["receipt_id"] == d["receipt_id"] and again["already_saved_transaction_id"] == save.json()["id"]
    dup = client.post("/api/spending", json={"amount": 31.07, "description": "x", "receipt_id": d["receipt_id"]})
    assert dup.json()["created"] is False and db_session.query(Receipt).count() == 1


def test_receipt_scan_degrades_gracefully(client, db_session, books):
    with patch("app.routers.spending._get_llm_provider", return_value=FakeVision(boom=True)):
        d = client.post("/api/spending/receipt/scan", files={"file": ("r.png", _jpeg((1, 2, 3)), "image/png")}).json()
    assert d["receipt_id"] and d["total"] is None and "Fill in the details" in d["warnings"][0]
    with patch("app.routers.spending._get_llm_provider", return_value=None):
        d = client.post("/api/spending/receipt/scan", files={"file": ("r.jpg", _jpeg((9, 9, 9)), "image/jpeg")}).json()
    assert "No AI provider" in d["warnings"][0]
    weird = FakeVision({"merchant": "X", "date": "1999-01-01", "total": "free"})
    with patch("app.routers.spending._get_llm_provider", return_value=weird):
        d = client.post("/api/spending/receipt/scan", files={"file": ("r.jpg", _jpeg((7, 7, 7)), "image/jpeg")}).json()
    assert d["date"] is None and d["total"] is None and any("total" in w for w in d["warnings"])


def test_receipt_upload_rejects_bad_files(client, books):
    r = client.post("/api/spending/receipt/scan", files={"file": ("x.exe", b"MZ\x90\x00binary", "application/octet-stream")})
    assert r.status_code == 422 and "photo" in r.json()["detail"]
    big = b"\xff\xd8\xff" + b"0" * (10 * 1024 * 1024)
    assert "10 MB" in client.post("/api/spending/receipt/scan", files={"file": ("b.jpg", big, "image/jpeg")}).json()["detail"]
    assert client.get("/api/spending/receipts/999").status_code == 404


# ---- API tokens and the ingest inbox ----

def test_tokens_are_admin_only_and_shown_once(client, db_session, books):
    assert client.post("/api/spending/tokens", json={"name": "Muse"}).status_code == 403
    _admin(db_session)
    created = client.post("/api/spending/tokens", json={"name": "Muse"}).json()
    assert created["token"].startswith("bb_")
    listed = client.get("/api/spending/tokens").json()
    assert listed[0]["name"] == "Muse" and "token" not in listed[0] and created["token"].startswith(listed[0]["prefix"])


@pytest.fixture
def anon(db_session):
    """A client with no session (the ingest endpoint uses its token, not a login)."""
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _token(client, db_session, name="Muse"):
    _admin(db_session)
    return client.post("/api/spending/tokens", json={"name": name}).json()


def test_ingest_requires_a_valid_token(client, db_session, books):
    tok = _token(client, db_session)
    app.dependency_overrides.pop(__import__("app.utils.auth", fromlist=["get_current_user"]).get_current_user, None)
    c = TestClient(app)
    body = {"amount": 12, "merchant": "Bar"}
    assert c.post("/api/ingest/spending", json=body).status_code == 401
    assert c.post("/api/ingest/spending", json=body, headers={"Authorization": "Bearer bb_wrong"}).status_code == 401
    ok = c.post("/api/ingest/spending", json=body, headers={"Authorization": f"Bearer {tok['token']}"})
    assert ok.status_code == 200
    # revoked tokens stop working
    from app.utils.auth import get_current_user
    from app.models import User
    app.dependency_overrides[get_current_user] = lambda: db_session.query(User).first()
    assert client.delete(f"/api/spending/tokens/{tok['id']}").status_code == 204
    app.dependency_overrides.pop(get_current_user)
    assert c.post("/api/ingest/spending", json=body, headers={"Authorization": f"Bearer {tok['token']}"}).status_code == 401


def test_ingest_goes_to_review_matches_names_and_dedupes(client, db_session, books):
    tok = _token(client, db_session)["token"]
    from app.utils.auth import get_current_user
    saved = app.dependency_overrides.pop(get_current_user)
    c = TestClient(app)
    h = {"Authorization": f"Bearer {tok}"}
    receipt = base64.b64encode(_jpeg((5, 6, 7))).decode()
    body = {"amount": 64.2, "merchant": "Keg Steakhouse", "category": "DINING", "business": "realesam",
            "external_id": "msg-123", "receipt_base64": receipt, "receipt_filename": "keg.jpg"}
    r = c.post("/api/ingest/spending", json=body, headers=h).json()
    assert r["status"] == "pending" and r["duplicate"] is False
    assert r["category_matched"] == "Dining" and r["business_matched"] == "Realesam"
    txn = db_session.get(Transaction, r["id"])
    assert txn.receipt_id and "Sent by: Muse" in txn.notes and txn.review_source == "api"

    again = c.post("/api/ingest/spending", json=body, headers=h).json()
    assert again["duplicate"] is True and again["id"] == r["id"]
    assert again["duplicate_reason"] == "external_id already received"

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    unknown = c.post("/api/ingest/spending", json={"amount": 9, "merchant": "Zoo", "category": "Animals",
                                                  "business": "Nope", "date": yesterday}, headers=h).json()
    assert db_session.get(Transaction, unknown["id"]).date.isoformat() == yesterday
    t2 = db_session.get(Transaction, unknown["id"])
    assert t2.category_id is None and "Suggested category: Animals" in t2.notes and "Suggested business: Nope" in t2.notes
    assert t2.entity_id == books["personal"].id
    bad = c.post("/api/ingest/spending", json={"amount": 9, "merchant": "Zoo", "receipt_base64": "%%%"}, headers=h)
    assert bad.status_code == 422

    # pending items don't count until approved; approval keeps the dedupe fingerprint
    ym = date.today().strftime("%Y-%m")
    assert month_overview(db_session, ym, books["realesam"].id).expense.actual == 0
    app.dependency_overrides[get_current_user] = saved
    assert client.put(f"/api/transactions/{r['id']}/review", json={"review_status": "confirmed"}).status_code == 200
    assert month_overview(db_session, ym, books["realesam"].id).expense.actual == 64.2
    app.dependency_overrides.pop(get_current_user)
    assert c.post("/api/ingest/spending", json=body, headers=h).json()["duplicate"] is True
    app.dependency_overrides[get_current_user] = saved
