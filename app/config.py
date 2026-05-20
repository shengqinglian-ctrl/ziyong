from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-5.1-mini"
    feishu_webhook_url: str = ""
    enable_openai_analysis: bool = False
    enable_feishu_push: bool = False
    scan_interval_seconds: int = 60
    watchlist: str = "NVDA,AAPL,TSLA,AMD,MSFT,SPY,QQQ"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.watchlist.split(",") if s.strip()]


settings = Settings()
