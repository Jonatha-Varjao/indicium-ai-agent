from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
if not (PROJECT_ROOT / "pyproject.toml").exists() and not (PROJECT_ROOT / "src").is_dir():
    PROJECT_ROOT = Path("/app") if Path("/app/pyproject.toml").exists() else Path.cwd()


class DataMode(str, Enum):
    LIVE = "live"
    PINNED = "pinned"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_api_key: str = Field(..., description="Google Gemini API key")
    tavily_api_key: str = Field(..., description="Tavily API key for news search")
    langfuse_public_key: str = Field(
        default="", description="Langfuse public key (optional — tracing disabled if empty)"
    )
    langfuse_secret_key: str = Field(
        default="", description="Langfuse secret key (optional — tracing disabled if empty)"
    )
    langfuse_host: str = Field(
        default="http://localhost:3000",
        description="Langfuse host URL",
    )
    data_mode: DataMode = Field(
        default=DataMode.PINNED,
        description="Pipeline data source mode: 'pinned' (reproducible) or 'live' (freshness-check)",
    )
    timezone: str = Field(
        default="America/Sao_Paulo",
        description="Timezone for all timestamps in the report",
    )

    llm_model: str = Field(
        default="gemini-3.1-flash-lite",
        description="Google Gemini model identifier",
    )

    llm_temperature: float = Field(
        default=0.2,
        description="Temperature for the LLM narrative synthesis call",
    )

    project_root: Path = Field(
        default=PROJECT_ROOT, description="Project root directory"
    )

    @property
    def data_raw_dir(self) -> Path:
        return self.project_root / "data" / "raw"

    @property
    def data_cache_dir(self) -> Path:
        return self.project_root / "data" / "cache"

    @property
    def data_processed_dir(self) -> Path:
        return self.project_root / "data" / "processed"

    @property
    def output_charts_dir(self) -> Path:
        return self.project_root / "outputs" / "charts"

    @property
    def output_reports_dir(self) -> Path:
        return self.project_root / "outputs" / "reports"

    @property
    def output_audit_dir(self) -> Path:
        return self.project_root / "outputs" / "logs"

    @property
    def datasus_resource_url(self) -> str:
        return (
            "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br"
            "/SRAG/2026/INFLUD26-20-07-2026.csv"
        )

    @property
    def datasus_url_pattern(self) -> str:
        return (
            "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br"
            "/SRAG/{year}/INFLUD{year_short:02d}-{day:02d}-{month:02d}-{year}.csv"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
