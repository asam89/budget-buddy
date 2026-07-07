"""Tests for PR7: LLM provider abstraction + settings."""

import json
from unittest.mock import patch, MagicMock

from app.models import AppSetting
from app.services.llm import (
    OllamaProvider, AnthropicProvider, get_provider, LLMHealth,
)


# ---- Provider factory ----

def test_get_provider_ollama_default():
    provider = get_provider()
    assert provider is not None
    assert isinstance(provider, OllamaProvider)
    assert "ollama" in provider.name()


def test_get_provider_anthropic():
    provider = get_provider(provider_name="anthropic", anthropic_api_key="sk-test")
    assert provider is not None
    assert isinstance(provider, AnthropicProvider)
    assert "anthropic" in provider.name()


def test_get_provider_anthropic_no_key():
    provider = get_provider(provider_name="anthropic", anthropic_api_key="")
    assert provider is None


# ---- OllamaProvider ----

def test_ollama_name():
    p = OllamaProvider(model="gemma3:12b")
    assert p.name() == "ollama:gemma3:12b"


def test_ollama_health_unreachable():
    p = OllamaProvider(base_url="http://localhost:99999", model="test")
    health = p.health()
    assert not health.reachable
    assert health.error is not None


def test_ollama_list_models_unreachable():
    p = OllamaProvider(base_url="http://localhost:99999")
    assert p.list_models() == []


@patch("app.services.llm.requests.post")
def test_ollama_complete_json(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "message": {"content": '[{"date":"2026-01-01","amount":100,"name":"Test"}]'}
    }
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    p = OllamaProvider(model="test")
    result = p.complete_json("test prompt")
    assert isinstance(result, list)
    assert result[0]["name"] == "Test"


@patch("app.services.llm.requests.post")
def test_ollama_complete_json_markdown_fencing(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "message": {"content": '```json\n[{"date":"2026-01-01","amount":100,"name":"Test"}]\n```'}
    }
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    p = OllamaProvider(model="test")
    result = p.complete_json("test prompt")
    assert isinstance(result, list)
    assert len(result) == 1


@patch("app.services.llm.requests.post")
def test_ollama_complete_json_retry_on_invalid(mock_post):
    """First call returns invalid JSON, retry succeeds."""
    bad_resp = MagicMock()
    bad_resp.json.return_value = {"message": {"content": "not valid json"}}
    bad_resp.raise_for_status = MagicMock()

    good_resp = MagicMock()
    good_resp.json.return_value = {"message": {"content": '[]'}}
    good_resp.raise_for_status = MagicMock()

    mock_post.side_effect = [bad_resp, good_resp]

    p = OllamaProvider(model="test")
    result = p.complete_json("test prompt")
    assert result == []
    assert mock_post.call_count == 2


# ---- AnthropicProvider ----

def test_anthropic_name():
    p = AnthropicProvider(api_key="sk-test", model="claude-sonnet-4-20250514")
    assert "anthropic" in p.name()
    assert "claude" in p.name()


# ---- Settings API ----

def test_get_llm_settings(client, db_session):
    resp = client.get("/api/settings/llm")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "ollama"
    assert "ollama_base_url" in data
    assert "ollama_model" in data


def test_update_llm_settings(client, db_session):
    resp = client.put("/api/settings/llm", json={"ollama_model": "llama3:8b"})
    assert resp.status_code == 200
    assert resp.json()["ollama_model"] == "llama3:8b"

    # Verify persisted
    resp = client.get("/api/settings/llm")
    assert resp.json()["ollama_model"] == "llama3:8b"


def test_update_llm_provider_invalid(client, db_session):
    resp = client.put("/api/settings/llm", json={"provider": "openai"})
    assert resp.status_code == 422


def test_update_llm_provider_anthropic_no_key(client, db_session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        resp = client.put("/api/settings/llm", json={"provider": "anthropic"})
        assert resp.status_code == 422
        assert "ANTHROPIC_API_KEY" in resp.json()["detail"]
    finally:
        get_settings.cache_clear()


def test_llm_health_endpoint(client, db_session):
    resp = client.get("/api/settings/llm/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "reachable" in data
    assert "provider_name" in data


def test_llm_models_endpoint(client, db_session):
    resp = client.get("/api/settings/llm/models")
    assert resp.status_code == 200
    assert "models" in resp.json()


def test_db_settings_override(client, db_session):
    """AppSetting DB values override env defaults."""
    db_session.add(AppSetting(key="ollama_model", value="custom:7b"))
    db_session.commit()

    resp = client.get("/api/settings/llm")
    assert resp.json()["ollama_model"] == "custom:7b"
