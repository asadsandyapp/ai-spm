from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "AI-SPM Platform"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Public web/app base used in verification email links (not the API host).
    app_base_url: str = "http://localhost:5173"
    # Public Kong/gateway URL stamped into agent enrollment packages (local or cloud).
    # Env: AISPM_PUBLIC_GATEWAY_URL
    aispm_public_gateway_url: str = "http://localhost:8090"
    # Directory of prebuilt Linux installer assets for Download Agent package.
    # Env: AISPM_INSTALLER_LINUX_DIR
    aispm_installer_linux_dir: str = "/opt/ai-spm/installer-linux"
    # HMAC key material for sealed installer builds (optional; falls back to JWT secret).
    # Env: AISPM_INSTALLER_SIGNING_KEY
    aispm_installer_signing_key: str = ""

    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://aispm:aispm@localhost:5432/aispm"
    )
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")

    jwt_secret_key: str = Field(default="CHANGE_ME_IN_PRODUCTION_USE_VAULT")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    platform_jwt_secret_key: str = Field(default="CHANGE_ME_PLATFORM_SECRET")
    platform_jwt_algorithm: str = "HS256"
    platform_jwt_expire_minutes: int = 480

    email_verification_expire_hours: int = 48
    signup_rate_limit_per_ip: int = 5

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_enabled: bool = False

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",
        ]
    )

    default_starter_max_agents: int = 25
    default_starter_max_prompts_per_month: int = 50_000
    default_professional_max_agents: int = 150
    default_professional_max_prompts_per_month: int = 500_000
    default_enterprise_max_agents: int = 0  # unlimited
    default_enterprise_max_prompts_per_month: int = 0  # unlimited
    past_due_grace_days: int = 7
    stripe_price_starter: str = "starter_monthly"
    stripe_price_professional: str = "professional_monthly"
    stripe_price_enterprise: str = "enterprise_monthly"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "aispm"
    minio_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
