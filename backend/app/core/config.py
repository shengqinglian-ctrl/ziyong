from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "A-Stock Watcher"
    database_url: str = "sqlite:///./data/a_stock_watcher.db"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    alert_cooldown_seconds: int = 300
    auto_quote_refresh_enabled: bool = True
    auto_quote_refresh_seconds: int = 30
    analysis_model_provider: str = "local"
    analysis_model_timeout_seconds: float = 8.0
    chat_model_timeout_seconds: float = 180.0
    local_model_base_url: str = "http://127.0.0.1:11434"
    local_model_name: str = "qwen2.5:7b"
    github_models_token: str | None = None
    github_models_base_url: str = "https://models.github.ai/inference"
    github_models_model: str = "openai/gpt-4.1-mini"
    analysis_cache_ttl_seconds: int = 900
    notification_cooldown_seconds: int = 300

    model_config = SettingsConfigDict(env_file=".env", env_prefix="ASW_")


@lru_cache
def get_settings() -> Settings:
    return Settings()
