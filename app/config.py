import logging
import secrets
import warnings
from functools import lru_cache

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

DEFAULT_DB_PASSPHRASE = "change-me-to-a-random-secret"


class Settings(BaseSettings):
    # Database
    database_path: str = "./data/budget_buddy.db"
    db_passphrase: str = DEFAULT_DB_PASSPHRASE

    # Auth
    secret_key: str = ""
    admin_username: str = "admin"
    admin_password_hash: str = ""  # set on first run

    # Plaid
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"

    # Anthropic (for AI statement parsing — opt-in fallback only)
    anthropic_api_key: str = ""

    # LLM provider config
    llm_provider: str = "ollama"  # 'ollama' | 'anthropic'
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma3:12b"
    llm_timeout_seconds: int = 120

    # Google Sheets (optional)
    google_credentials_path: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Security. Set cookie_secure=True when serving over HTTPS so the session
    # cookie is only sent on encrypted connections. csrf_protect rejects
    # cross-origin state-changing requests (defense-in-depth on top of the
    # SameSite=Lax cookie); leave on unless a trusted cross-origin client needs it.
    cookie_secure: bool = False
    csrf_protect: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def _validate_settings(settings: "Settings") -> None:
    """Warn loudly about insecure defaults and ensure a stable secret key.

    Budget Buddy is meant to be reachable across a home network, so weak
    defaults are a real risk. We don't hard-fail (to keep first-run/dev easy),
    but we emit prominent warnings the operator can't miss.
    """
    if settings.db_passphrase == DEFAULT_DB_PASSPHRASE:
        warnings.warn(
            "DB_PASSPHRASE is set to the built-in default. Your database is "
            "effectively unencrypted. Set a strong DB_PASSPHRASE in .env "
            "(generate one with: python -c \"import secrets; print(secrets.token_hex(32))\").",
            stacklevel=2,
        )
        logger.warning("Insecure default DB_PASSPHRASE in use.")

    if not settings.secret_key:
        # No SECRET_KEY provided: fall back to an ephemeral one so the app
        # still runs, but sessions won't survive a restart. Warn the operator.
        settings.secret_key = secrets.token_hex(32)
        warnings.warn(
            "SECRET_KEY is not set; using a random ephemeral key. All sessions "
            "will be invalidated on restart. Set SECRET_KEY in .env for a stable "
            "deployment.",
            stacklevel=2,
        )
        logger.warning("SECRET_KEY not set; using ephemeral key.")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    _validate_settings(settings)
    return settings
