from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    supabase_auth_enabled: bool = False
    supabase_url: str = ""
    supabase_publishable_key: str = ""

    search_provider: Literal["exa", "tavily"] = "exa"
    exa_api_key: SecretStr = SecretStr("")
    tavily_api_key: SecretStr = SecretStr("")
    llm_api_key: SecretStr = SecretStr("")
    llm_provider: str = "none"
    llm_model: str = ""
    live_request_timeout_seconds: float = Field(default=20, ge=1, le=120)
    live_cache_ttl_seconds: int = Field(default=180, ge=0, le=3600)
    log_level: str = "INFO"
    credit_search_confirmed_free: bool = False
    database_path: str = str(ROOT / "data" / "daily_mind.sqlite3")
    daily_generation_enabled: bool = True
    daily_generation_interval_seconds: int = Field(default=60, ge=1, le=3600)
    daily_generation_retry_seconds: int = Field(default=300, ge=1, le=3600)
    offline_news_max_age_days: int = Field(default=7, ge=1, le=30)
    story_semantic_enabled: bool = True
    story_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    story_model_cache: str = str(Path.home() / ".cache" / "daily-mind-models")
    story_similarity_threshold: float = Field(default=0.68, ge=0, le=1)

    @property
    def search_configured(self) -> bool:
        key = self.exa_api_key if self.search_provider == "exa" else self.tavily_api_key
        return bool(key.get_secret_value().strip())
