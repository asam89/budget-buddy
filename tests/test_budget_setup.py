"""Tests for AI-assisted budget setup."""

import io
import json
from unittest.mock import patch

import pandas as pd

from app.models import Budget, Category
from app.services.budget_setup import (
    analyze_stream,
    commit_budget,
    normalize_to_monthly,
    parse_budget_dataframe,
    propose_budget,
)
from app.services.llm import LLMHealth


class FakeProvider:
    """Test double for LLMProvider."""

    def __init__(self, items, reachable=True, available=True):
        self._items = items
        self._reachable = reachable
        self._available = available
        self.calls = 0

    def name(self):
        return "ollama:fake-model"

    def health(self):
        return LLMHealth(
            reachable=self._reachable,
            model_available=self._available,
            latency_ms=1.0,
            error=None,
        )

    def complete_json(self, prompt, schema=None, max_tokens=4096):
        self.calls += 1
        return {"items": self._items}


# ---- parsing ----

def test_parse_budget_dataframe_label_amount():
    df = pd.DataFrame([
        ["Expense", "Amount"],
        ["Rent", "2200"],
        ["Groceries", "800"],
        ["Total", "3000"],
    ])
    items = parse_budget_dataframe(df)
    labels = {i["label"]: i["amount"] for i in items}
    assert labels == {"Rent": 2200.0, "Groceries": 800.0}  # Total row dropped


def test_parse_budget_dataframe_with_period_column():
    df = pd.DataFrame([
        ["Item", "Cost", "Frequency"],
        ["Insurance", "1200", "annual"],
        ["Netflix", "16", "monthly"],
    ])
    items = parse_budget_dataframe(df)
    by_label = {i["label"]: i for i in items}
    assert by_label["Insurance"]["period_hint"] == "annual"
    assert by_label["Netflix"]["period_hint"] == "monthly"


def test_parse_budget_dataframe_currency_symbols():
    df = pd.DataFrame([
        ["Category", "Monthly"],
        ["Rent", "$2,200.00"],
    ])
    items = parse_budget_dataframe(df)
    assert items[0]["amount"] == 2200.0


# ---- period normalization ----

def test_normalize_to_monthly():
    assert normalize_to_monthly(1200, "annual") == 100.0
    assert normalize_to_monthly(300, "quarterly") == 100.0
    assert normalize_to_monthly(100, "monthly") == 100.0
    assert normalize_to_monthly(100, None) == 100.0
    assert normalize_to_monthly(100, "weekly") == 433.33


# ---- proposal ----

def test_propose_budget_uses_llm_when_reachable(db_session):
    db_session.add(Category(name="Housing"))
    db_session.commit()
    items = [{"label": "Rent", "amount": 2200.0, "period_hint": None}]
    provider = FakeProvider([
        {"label": "Rent", "category": "Housing", "monthly_amount": 2200.0,
         "period": "monthly", "kind": "expense", "confidence": 0.95, "note": ""}
    ])
    result = propose_budget(db_session, items, provider=provider)
    assert result["ai_used"] is True
    assert result["assisting_model"] == "ollama:fake-model"
    assert result["items"][0]["category"] == "Housing"
    assert result["items"][0]["monthly_amount"] == 2200.0


def test_propose_budget_falls_back_to_heuristic_when_unreachable(db_session):
    db_session.add(Category(name="Groceries"))
    db_session.commit()
    items = [{"label": "Groceries", "amount": 800.0, "period_hint": "monthly"}]
    provider = FakeProvider([], reachable=False)
    result = propose_budget(db_session, items, provider=provider)
    assert result["ai_used"] is False
    # heuristic keyword-matches the existing "Groceries" category
    assert result["items"][0]["category"] == "Groceries"
    assert result["items"][0]["monthly_amount"] == 800.0


def test_propose_budget_normalizes_when_llm_omits_amount(db_session):
    items = [{"label": "Insurance", "amount": 1200.0, "period_hint": "annual"}]
    # LLM returns category but no monthly_amount -> fall back to normalization
    provider = FakeProvider([
        {"label": "Insurance", "category": "Insurance", "period": "annual",
         "kind": "expense", "confidence": 0.8, "note": ""}
    ])
    result = propose_budget(db_session, items, provider=provider)
    assert result["items"][0]["monthly_amount"] == 100.0


# ---- streaming progress ----

def test_analyze_stream_emits_stages_and_final_payload(db_session):
    db_session.add(Category(name="Housing"))
    db_session.commit()
    items = [{"label": "Rent", "amount": 2200.0, "period_hint": None}]
    provider = FakeProvider([
        {"label": "Rent", "category": "Housing", "monthly_amount": 2200.0,
         "period": "monthly", "kind": "expense", "confidence": 0.95, "note": ""}
    ])
    events = list(analyze_stream(db_session, items, provider=provider))
    stages = [e["stage"] for e in events]
    # ordered pipeline, ending in the completed payload
    assert stages[0] == "parsed"
    assert "checking_model" in stages
    assert "calling_model" in stages
    assert "model_done" in stages
    assert stages[-1] == "complete"
    # calling_model precedes model_done (the slow step is bracketed)
    assert stages.index("calling_model") < stages.index("model_done")
    final = events[-1]["detail"]
    assert final["ai_used"] is True
    assert final["items"][0]["category"] == "Housing"


def test_analyze_stream_reports_heuristic_when_offline(db_session):
    items = [{"label": "Rent", "amount": 2200.0, "period_hint": None}]
    provider = FakeProvider([], reachable=False)
    events = list(analyze_stream(db_session, items, provider=provider))
    stages = [e["stage"] for e in events]
    assert "heuristic" in stages
    assert "calling_model" not in stages
    assert events[-1]["detail"]["ai_used"] is False


def test_analyze_stream_endpoint_streams_sse(client):
    tsv = "Expense\tAmount\nRent\t2200\n"
    fake = FakeProvider([
        {"label": "Rent", "category": "Housing", "monthly_amount": 2200.0,
         "period": "monthly", "kind": "expense", "confidence": 0.9, "note": ""},
    ])
    with patch("app.services.budget_setup._get_llm_provider", return_value=fake):
        resp = client.post("/api/budget-setup/analyze-paste-stream", data={"text": tsv})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = [
        json.loads(line[len("data: "):])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    stages = [e["stage"] for e in events]
    assert stages[0] == "parsed"
    assert stages[-1] == "complete"
    assert events[-1]["detail"]["items"][0]["category"] == "Housing"


# ---- commit ----

def test_commit_budget_creates_categories_and_budgets(db_session):
    items = [
        {"category": "Housing", "monthly_amount": 2200.0, "kind": "expense"},
        {"category": "Food", "monthly_amount": 800.0, "kind": "expense"},
    ]
    stats = commit_budget(db_session, items)
    assert stats["categories_created"] == 2
    assert stats["budgets_created"] == 2
    budgets = db_session.query(Budget).all()
    assert len(budgets) == 2


def test_commit_budget_aggregates_same_category(db_session):
    items = [
        {"category": "Subscriptions", "monthly_amount": 16.0, "kind": "expense"},
        {"category": "Subscriptions", "monthly_amount": 10.0, "kind": "expense"},
    ]
    stats = commit_budget(db_session, items)
    assert stats["budgets_created"] == 1
    budget = db_session.query(Budget).first()
    assert budget.monthly_limit == 26.0


def test_commit_budget_upserts_existing(db_session):
    cat = Category(name="Housing")
    db_session.add(cat)
    db_session.flush()
    db_session.add(Budget(category_id=cat.id, monthly_limit=1000.0))
    db_session.commit()

    stats = commit_budget(db_session, [
        {"category": "Housing", "monthly_amount": 2200.0, "kind": "expense"},
    ])
    assert stats["budgets_updated"] == 1
    assert stats["budgets_created"] == 0
    budget = db_session.query(Budget).filter(Budget.category_id == cat.id).first()
    assert budget.monthly_limit == 2200.0


def test_commit_budget_skips_income(db_session):
    items = [
        {"category": "Salary", "monthly_amount": 5000.0, "kind": "income"},
        {"category": "Rent", "monthly_amount": 2200.0, "kind": "expense"},
    ]
    stats = commit_budget(db_session, items)
    assert stats["income_items_skipped"] == 1
    assert stats["budgets_created"] == 1


# ---- endpoints ----

def test_analyze_paste_endpoint(client):
    tsv = "Expense\tAmount\nRent\t2200\nGroceries\t800\n"
    fake = FakeProvider([
        {"label": "Rent", "category": "Housing", "monthly_amount": 2200.0,
         "period": "monthly", "kind": "expense", "confidence": 0.9, "note": ""},
        {"label": "Groceries", "category": "Food", "monthly_amount": 800.0,
         "period": "monthly", "kind": "expense", "confidence": 0.9, "note": ""},
    ])
    with patch("app.services.budget_setup._get_llm_provider", return_value=fake):
        resp = client.post("/api/budget-setup/analyze-paste", data={"text": tsv})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ai_used"] is True
    assert body["assisting_model"] == "ollama:fake-model"
    assert len(body["items"]) == 2


def test_analyze_paste_empty(client):
    resp = client.post("/api/budget-setup/analyze-paste", data={"text": "   "})
    assert resp.status_code == 400


def test_commit_endpoint(client):
    resp = client.post("/api/budget-setup/commit", json={
        "items": [
            {"category": "Housing", "monthly_amount": 2200.0, "kind": "expense"},
        ]
    })
    assert resp.status_code == 200
    assert resp.json()["budgets_created"] == 1
