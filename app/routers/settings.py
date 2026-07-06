"""Settings router — LLM provider config, model management, health check."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.config import get_settings
from app.database import get_db
from app.models import User, AppSetting
from app.services.llm import get_provider, OllamaProvider
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/settings", tags=["settings"])


class LLMSettingsResponse(BaseModel):
    provider: str
    ollama_base_url: str
    ollama_model: str
    llm_timeout_seconds: int
    anthropic_configured: bool


class LLMSettingsUpdate(BaseModel):
    provider: Optional[str] = None
    ollama_model: Optional[str] = None
    ollama_base_url: Optional[str] = None


class LLMHealthResponse(BaseModel):
    provider_name: str
    reachable: bool
    model_available: bool
    latency_ms: float
    error: Optional[str] = None


def _get_setting(db: Session, key: str, default: str) -> str:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else default


def _set_setting(db: Session, key: str, value: str):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


@router.get("/llm", response_model=LLMSettingsResponse)
def get_llm_settings(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    settings = get_settings()
    return LLMSettingsResponse(
        provider=_get_setting(db, "llm_provider", settings.llm_provider),
        ollama_base_url=_get_setting(db, "ollama_base_url", settings.ollama_base_url),
        ollama_model=_get_setting(db, "ollama_model", settings.ollama_model),
        llm_timeout_seconds=settings.llm_timeout_seconds,
        anthropic_configured=bool(settings.anthropic_api_key),
    )


@router.put("/llm", response_model=LLMSettingsResponse)
def update_llm_settings(
    body: LLMSettingsUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    settings = get_settings()

    if body.provider is not None:
        if body.provider not in ("ollama", "anthropic"):
            raise HTTPException(status_code=422, detail="Provider must be 'ollama' or 'anthropic'")
        if body.provider == "anthropic" and not settings.anthropic_api_key:
            raise HTTPException(status_code=422, detail="ANTHROPIC_API_KEY not set in environment")
        _set_setting(db, "llm_provider", body.provider)

    if body.ollama_model is not None:
        _set_setting(db, "ollama_model", body.ollama_model)

    if body.ollama_base_url is not None:
        _set_setting(db, "ollama_base_url", body.ollama_base_url)

    db.commit()

    return LLMSettingsResponse(
        provider=_get_setting(db, "llm_provider", settings.llm_provider),
        ollama_base_url=_get_setting(db, "ollama_base_url", settings.ollama_base_url),
        ollama_model=_get_setting(db, "ollama_model", settings.ollama_model),
        llm_timeout_seconds=settings.llm_timeout_seconds,
        anthropic_configured=bool(settings.anthropic_api_key),
    )


@router.get("/llm/health", response_model=LLMHealthResponse)
def llm_health(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    settings = get_settings()
    provider_name = _get_setting(db, "llm_provider", settings.llm_provider)
    ollama_model = _get_setting(db, "ollama_model", settings.ollama_model)
    ollama_base_url = _get_setting(db, "ollama_base_url", settings.ollama_base_url)

    provider = get_provider(
        provider_name=provider_name,
        ollama_base_url=ollama_base_url,
        ollama_model=ollama_model,
        anthropic_api_key=settings.anthropic_api_key,
        llm_timeout=settings.llm_timeout_seconds,
    )
    if not provider:
        return LLMHealthResponse(
            provider_name="none",
            reachable=False,
            model_available=False,
            latency_ms=0,
            error="No provider configured",
        )

    health = provider.health()
    return LLMHealthResponse(
        provider_name=provider.name(),
        reachable=health.reachable,
        model_available=health.model_available,
        latency_ms=health.latency_ms,
        error=health.error,
    )


@router.get("/llm/models")
def list_ollama_models(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    settings = get_settings()
    ollama_base_url = _get_setting(db, "ollama_base_url", settings.ollama_base_url)
    ollama_model = _get_setting(db, "ollama_model", settings.ollama_model)

    provider = OllamaProvider(base_url=ollama_base_url, model=ollama_model)
    models = provider.list_models()
    return {"models": models}


@router.post("/llm/test")
def test_llm(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Run a canned extraction on a sample statement snippet."""
    settings = get_settings()
    provider_name = _get_setting(db, "llm_provider", settings.llm_provider)
    ollama_model = _get_setting(db, "ollama_model", settings.ollama_model)
    ollama_base_url = _get_setting(db, "ollama_base_url", settings.ollama_base_url)

    provider = get_provider(
        provider_name=provider_name,
        ollama_base_url=ollama_base_url,
        ollama_model=ollama_model,
        anthropic_api_key=settings.anthropic_api_key,
        llm_timeout=settings.llm_timeout_seconds,
    )
    if not provider:
        raise HTTPException(status_code=422, detail="No LLM provider configured")

    sample = """STATEMENT PERIOD: Jan 1-31, 2026
01/05 COSTCO WHOLESALE   -125.43
01/08 SHELL GAS STATION    -52.10
01/15 PAYROLL DEPOSIT     +2,450.00
01/22 NETFLIX              -15.99"""

    import time
    start = time.time()
    try:
        from app.services.ai_parser import EXTRACTION_PROMPT
        result = provider.complete_json(EXTRACTION_PROMPT.format(text=sample))
        latency = round((time.time() - start) * 1000, 1)
        return {
            "success": True,
            "provider": provider.name(),
            "latency_ms": latency,
            "parsed_count": len(result) if isinstance(result, list) else 0,
            "result": result,
        }
    except Exception as e:
        latency = round((time.time() - start) * 1000, 1)
        return {
            "success": False,
            "provider": provider.name(),
            "latency_ms": latency,
            "error": str(e),
        }
