"""WS-D: deterministic findings, payload privacy, and validated AI narrative."""

import time
from datetime import date

import pytest

from app.models import Account, Budget, Category, ManualActual, Transaction
from app.services import insights as insights_mod
from app.services.insights import (
    allowed_numbers,
    build_findings,
    generate_insights,
    validate_narrative,
    verify_text,
    _load_prompt,
)

SECRET_MERCHANT = "SECRETMERCHANTXYZ"


@pytest.fixture(autouse=True)
def _clear_cache():
    insights_mod._CACHE.clear()
    yield
    insights_mod._CACHE.clear()


def _seed(db):
    acc = Account(name="Checking", account_type="depository", current_balance=0.0)
    db.add(acc)
    groceries = Category(name="Groceries", kind="expense")
    gas = Category(name="Gas", kind="expense")
    salary = Category(name="Salary", kind="income")
    db.add_all([groceries, gas, salary])
    db.flush()
    # Groceries: manual actual (1000) overrides the transaction sum (900)
    db.add(Transaction(account_id=acc.id, category_id=groceries.id, amount=900.0,
                       date=date(2026, 3, 10), name="grocery run",
                       merchant_name=SECRET_MERCHANT, review_status="confirmed"))
    db.add(ManualActual(category_id=groceries.id, year_month="2026-03", amount=1000.0))
    # Gas: transaction-derived, over its 120 budget
    db.add(Transaction(account_id=acc.id, category_id=gas.id, amount=150.0,
                       date=date(2026, 3, 5), name="fuel", review_status="confirmed"))
    db.add(Budget(category_id=gas.id, monthly_limit=120.0))
    # Salary income
    db.add(Transaction(account_id=acc.id, category_id=salary.id, amount=-5000.0,
                       date=date(2026, 3, 1), name="pay", review_status="confirmed"))
    db.commit()


class FakeProvider:
    def __init__(self, payload, fail=False):
        self.payload = payload
        self.fail = fail
        self.calls = 0

    def name(self):
        return "ollama:test-model"

    def complete_json(self, prompt, schema=None, max_tokens=4096):
        self.calls += 1
        self.last_prompt = prompt
        if self.fail:
            raise RuntimeError("model offline")
        return self.payload


def test_findings_exact_and_manual_not_summed(db_session):
    _seed(db_session)
    f = build_findings(db_session, "2026-03")
    # manual override wins: groceries = 1000 (not 900+1000)
    assert f["totals"]["expense_actual"] == 1150.0
    assert f["totals"]["income_actual"] == 5000.0
    assert f["totals"]["saved_actual"] == 3850.0
    names = {r["name"]: r for r in f["top_categories"]}
    assert names["Groceries"]["actual"] == 1000.0
    assert names["Gas"]["actual"] == 150.0
    # only Gas is over budget (Groceries has no budget -> not flagged)
    over = {r["name"] for r in f["over_budget"]}
    assert over == {"Gas"}
    assert f["over_budget"][0]["overage"] == 30.0
    # biggest change ranked by |delta|; both rose from 0
    assert f["biggest_changes"][0]["name"] == "Groceries"
    assert f["biggest_changes"][0]["delta"] == 1000.0


def test_payload_contains_no_merchant_or_transaction_detail(db_session):
    _seed(db_session)
    f = build_findings(db_session, "2026-03")
    import json
    assert SECRET_MERCHANT not in json.dumps(f)
    # and it must not leak through the prompt sent to the model either
    assert SECRET_MERCHANT not in _load_prompt(f)


def test_generate_provider_failure_keeps_findings(db_session):
    _seed(db_session)
    provider = FakeProvider(None, fail=True)
    res = generate_insights(db_session, provider, "2026-03")
    assert res["generated"] is False
    assert res["narrative"] is None
    assert res["findings"]["totals"]["expense_actual"] == 1150.0
    assert "unavailable" in res["error"].lower()


def test_generate_no_provider_is_not_a_fallback(db_session):
    _seed(db_session)
    res = generate_insights(db_session, None, "2026-03")
    assert res["generated"] is False
    assert res["model"] is None
    assert res["findings"]["totals"]["expense_actual"] == 1150.0


def test_valid_narrative_generated_and_cached(db_session):
    _seed(db_session)
    payload = {"summary": "You spent $1,150 this month.",
               "bullets": ["Gas was over budget by $30."]}
    provider = FakeProvider(payload)
    res = generate_insights(db_session, provider, "2026-03")
    assert res["generated"] is True
    assert res["narrative"]["summary"].startswith("You spent")
    assert res["model"] == "ollama:test-model"
    assert provider.calls == 1
    # second call (not forced) is served from cache without hitting the model
    again = generate_insights(db_session, provider, "2026-03")
    assert again["cached"] is True
    assert provider.calls == 1


def test_unverifiable_numbers_are_discarded(db_session):
    _seed(db_session)
    payload = {
        "summary": "You spent $99999 this month.",   # fabricated -> dropped
        "bullets": [
            "Gas was over budget by $30.",            # valid -> kept
            "Groceries jumped by $4321.",             # fabricated -> dropped
        ],
    }
    provider = FakeProvider(payload)
    res = generate_insights(db_session, provider, "2026-03")
    assert res["narrative"]["summary"] == ""
    assert res["narrative"]["bullets"] == ["Gas was over budget by $30."]
    assert res["narrative"]["dropped"] == 2


def test_regeneration_updates_timestamp(db_session):
    _seed(db_session)
    payload = {"summary": "You spent $1,150 this month.", "bullets": []}
    provider = FakeProvider(payload)
    first = generate_insights(db_session, provider, "2026-03")
    time.sleep(1.1)  # timestamps have second resolution
    second = generate_insights(db_session, provider, "2026-03", force=True)
    assert second["generated"] is True
    assert second["generated_at"] != first["generated_at"]
    assert provider.calls == 2


def test_verify_text_helpers(db_session):
    _seed(db_session)
    f = build_findings(db_session, "2026-03")
    allowed = allowed_numbers(f)
    assert verify_text("Total was $1,150.", allowed)
    assert not verify_text("Total was $777.", allowed)
    # validate_narrative drops the bad line
    out = validate_narrative({"summary": "ok $1,150", "bullets": ["bad $777"]}, f)
    assert out["summary"] == "ok $1,150"
    assert out["bullets"] == []


def test_findings_endpoint_is_nonblocking(client, db_session, monkeypatch):
    _seed(db_session)

    # If the findings endpoint ever resolved a provider, this would blow up.
    def _boom(_db):
        raise AssertionError("findings endpoint must not touch the LLM provider")

    monkeypatch.setattr("app.routers.insights._get_llm_provider", _boom)
    r = client.get("/api/insights/findings?year_month=2026-03")
    assert r.status_code == 200
    body = r.json()
    assert body["findings"]["totals"]["expense_actual"] == 1150.0
    assert body["has_cached_narrative"] is False
