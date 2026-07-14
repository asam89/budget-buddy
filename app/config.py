import secrets
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_path: str = "./data/budget_buddy.db"
    db_passphrase: str = "change-me-to-a-random-secret"

    # Auth
    secret_key: str = secrets.token_hex(32)
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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
