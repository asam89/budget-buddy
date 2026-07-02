from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"
    secret_key: str = "change-me-to-a-random-secret"
    database_url: str = "sqlite:///./data/budget_buddy.db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
