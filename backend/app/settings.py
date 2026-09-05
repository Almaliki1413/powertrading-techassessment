from __future__ import annotations

from pathlib import Path

from pydantic import Field, HttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / ".env.example"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    data_dir: Path = Field(default=ROOT / "data", alias="BESS_DATA_DIR")
    source_mode: str = Field(default="pinned", alias="BESS_SOURCE_MODE")
    aemo_base_url: str = Field(
        default="https://nemweb.com.au/Reports/Archive/DispatchIS_Reports/",
        alias="BESS_AEMO_BASE_URL",
    )
    max_range_days: int = Field(default=31, alias="BESS_MAX_RANGE_DAYS")
    http_connect_timeout_s: float = Field(default=5, alias="BESS_HTTP_CONNECT_TIMEOUT_S")
    http_read_timeout_s: float = Field(default=60, alias="BESS_HTTP_READ_TIMEOUT_S")
    http_retries: int = Field(default=2, alias="BESS_HTTP_RETRIES")
    solver_timeout_s: float = Field(default=30, alias="BESS_SOLVER_TIMEOUT_S")
    max_concurrent_solves: int = Field(default=1, alias="BESS_MAX_CONCURRENT_SOLVES")
    queue_timeout_s: float = Field(default=10, alias="BESS_QUEUE_TIMEOUT_S")
    log_level: str = Field(default="INFO", alias="BESS_LOG_LEVEL")
    dev_cors_origin: str = Field(default="http://127.0.0.1:5173", alias="BESS_DEV_CORS_ORIGIN")

    @model_validator(mode="after")
    def resolve_relative_paths(self) -> Settings:
        if not self.data_dir.is_absolute():
            self.data_dir = (ROOT / self.data_dir).resolve()
        return self

    @property
    def pinned_dir(self) -> Path:
        return self.data_dir / "pinned"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def manifest_path(self) -> Path:
        return self.pinned_dir / "manifest.json"

    @property
    def frontend_dist(self) -> Path:
        return ROOT / "frontend" / "dist"

    @property
    def allowlisted_base(self) -> HttpUrl:
        return HttpUrl(self.aemo_base_url)


def get_settings() -> Settings:
    return Settings()
