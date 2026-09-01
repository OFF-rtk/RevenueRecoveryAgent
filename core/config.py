"""
core/config.py
──────────────
All configuration is loaded from environment variables (via .env).
Fails loudly at startup if any required variable is absent.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Postgres ────────────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://recovery:recovery@localhost:5434/recovery_agent"
    )

    @field_validator("database_url")
    @classmethod
    def fix_postgres_scheme(cls, v: str) -> str:
        # Render sets database URL as postgres://...
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # ── Razorpay ─────────────────────────────────────────────────
    razorpay_webhook_secret: str = "changeme"

    # ── Groq ────────────────────────────────────────────────────
    groq_api_key: str  # required — no default
    groq_base_url: str = "https://api.groq.com"
    # Tier 1: cheap, high-volume (8B-class)
    groq_tier1_model: str = "openai/gpt-oss-20b"
    # Tier 2: escalation, complex reasoning (120B-class)
    groq_tier2_model: str = "openai/gpt-oss-120b"

    # ── App ─────────────────────────────────────────────────────
    log_level: str = "INFO"
    app_env: str = "development"

    # ── WhatsApp (Meta Cloud API) ───────────────────────────────
    whatsapp_token: str = ""
    phone_number_id: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    use_mock_channel: bool = False


# Module-level singleton — imported throughout the codebase.
# Instantiation here means a missing required var raises ValidationError
# at import time (i.e. at startup), not silently at runtime.
settings = Settings()
