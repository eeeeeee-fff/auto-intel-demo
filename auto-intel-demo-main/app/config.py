from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Auto Intel Demo"
    app_host: str = "127.0.0.1"
    app_port: int = 8018
    database_url: str = f"sqlite:///{(DATA_DIR / 'demo.db').as_posix()}"
    scheduler_enabled: bool = False
    scheduler_trigger: str = "cron"
    scheduler_timezone: str = "Asia/Shanghai"
    scheduler_interval_minutes: int = 60
    scheduler_cron_hour: int = 5
    scheduler_cron_minute: int = 0
    briefing_followup_days: int = 5
    collect_limit_per_source: int = 12
    lookback_hours: int = 72
    request_timeout_seconds: int = 20
    llm_timeout_seconds: int = 120

    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
