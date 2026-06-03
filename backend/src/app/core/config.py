from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", ROOT_DIR / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Project .env is authoritative for this local app so stale PowerShell
        # session variables cannot silently override model keys.
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)

    app_name: str = "AgentHub"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"

    secret_key: str = "agenthub-dev-secret-change-me"
    access_token_expire_minutes: int = 60 * 24

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_port: int = 5173

    cors_origins: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def populate_cors_origins(self) -> "Settings":
        """当 cors_origins 未通过环境变量指定时，根据 frontend_port 动态填充默认值。"""
        if not self.cors_origins:
            self.cors_origins = [
                f"http://localhost:{self.frontend_port}",
                f"http://127.0.0.1:{self.frontend_port}",
                "http://localhost:4173",
                "http://127.0.0.1:4173",
            ]
        return self

    redis_url: str = "redis://localhost:6380/0"

    # 以下 Ark 相关配置已弃用（deprecated），保留作为迁移期 fallback。
    # 新代码请通过数据库 ModelProvider / ModelConfig 配置。
    # 见 app/services/model_config_resolver.py
    llm_provider: Literal["auto", "ark", "mock"] = "auto"
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_api_key: str | None = None
    ark_endpoint_id: str | None = None
    ark_model: str | None = "doubao-seed-2-0-lite"
    ark_timeout_seconds: float = 60
    ark_stream_timeout_seconds: float = 120

    demo_email: str = "demo@agenthub.local"
    demo_username: str = "demo"
    demo_password: str = "agenthub"

    artifact_base_url: str = "http://localhost:8000"
    storage_dir: str = str(ROOT_DIR / "var" / "storage")
    max_upload_mb: int = 50

    enable_function_calling: bool = True

    @property
    def model_candidates(self) -> list[str]:
        candidates = [self.ark_endpoint_id, self.ark_model]
        result: list[str] = []
        for item in candidates:
            if item and item not in result:
                result.append(item)
        return result or ["mock-model"]

    @property
    def use_mock_llm(self) -> bool:
        if self.llm_provider == "mock":
            return True
        if self.llm_provider == "ark":
            return False
        return not bool(self.ark_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
