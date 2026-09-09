from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", API_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "gemini_key"),
    )
    gemini_model: str = Field(
        default="gemini-3.5-flash-lite",
        validation_alias="GEMINI_MODEL",
    )
    gemini_timeout_seconds: float = Field(
        default=20.0,
        gt=0,
        le=60,
        validation_alias="GEMINI_TIMEOUT_SECONDS",
    )
    juso_confirm_key: SecretStr | None = Field(
        default=None,
        validation_alias="JUSO_CONFIRM_KEY",
    )
    data_go_kr_service_key: SecretStr | None = Field(
        default=None,
        validation_alias="DATA_GO_KR_SERVICE_KEY",
    )
    public_api_timeout_seconds: float = Field(
        default=15.0,
        gt=0,
        le=60,
        validation_alias="PUBLIC_API_TIMEOUT_SECONDS",
    )
    public_market_months: int = Field(
        default=12,
        ge=1,
        le=24,
        validation_alias="PUBLIC_MARKET_MONTHS",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
