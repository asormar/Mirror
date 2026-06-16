from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "CopyTrade Sim"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = Field(
        default="postgresql+asyncpg://copytrade:copytrade@localhost:5432/copytrade"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    jwt_secret: str = "change-me-to-a-32-byte-random-string"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expires_min: int = 60
    jwt_refresh_token_expires_days: int = 14

    sec_edgar_user_agent: str = "CopyTradeSim research@example.com"
    sec_edgar_rate_limit_per_sec: int = 8

    initial_virtual_capital: float = 100000.00


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
