"""
ZionhiltPay — application configuration.
All secrets/config are loaded from environment variables (.env in dev,
real secret manager in production). Nothing sensitive is hardcoded.
"""
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    APP_NAME: str = "ZionhiltPay"
    APP_ENV: str = "development"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://zionhilt:zionhilt@db:5432/zionhiltpay"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://zionhilt:zionhilt@db:5432/zionhiltpay"

    # --- Security / JWT ---
    JWT_SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_super_secret_key_min_32_chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # Fernet key used to encrypt government ID numbers at rest. REQUIRED in production.
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # In development, if empty, a key is derived from JWT_SECRET_KEY (so rotating the JWT secret
    # would make stored IDs unreadable - set this explicitly before storing real data).
    DATA_ENCRYPTION_KEY: str = ""
    PIN_MAX_FAILED_ATTEMPTS: int = 3
    PIN_LOCK_MINUTES: int = 30

    # --- OTP ---
    OTP_LENGTH: int = 6
    OTP_EXPIRE_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 5
    OTP_RESEND_COOLDOWN_SECONDS: int = 60

    # --- Email (mock/console by default; swap for real SMTP in production) ---
    EMAIL_PROVIDER: str = "console"  # console | smtp
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "no-reply@zionhiltpay.local"

    # --- SMS (mock/console by default; swap for Termii/Twilio in production) ---
    SMS_PROVIDER: str = "console"  # console | termii | twilio
    SMS_API_KEY: str = ""
    SMS_SENDER_ID: str = "ZionhiltPay"

    # --- CORS ---
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # --- Rate limiting ---
    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_OTP: str = "5/minute"
    RATE_LIMIT_LOOKUP: str = "20/minute"  # username availability + recipient name enquiry

    # --- Business rules (fallback defaults; live values in platform_config table) ---
    REWARD_RATE: float = 0.0050
    INSURANCE_CONTRIBUTION_RATE: float = 0.0100
    TRANSACTION_FEE_RATE: float = 0.0150
    WITHDRAWAL_FEE_FLAT: float = 25.00

    # --- AI agents (Claude) ---
    # Leave ANTHROPIC_API_KEY empty to disable all agent endpoints (they return 503).
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"
    AGENT_MODEL: str = "claude-sonnet-5-5"
    AGENT_MAX_TOKENS: int = 1024
    AGENT_MAX_TOOL_ROUNDS: int = 5
    AGENT_MAX_HISTORY_TURNS: int = 10
    AGENT_MAX_MESSAGE_CHARS: int = 2000
    RATE_LIMIT_AGENT: str = "20/minute"

    # --- Mock payment gateway ---
    MOCK_GATEWAY_SUCCESS_RATE: float = 0.95
    MOCK_GATEWAY_LATENCY_MS: int = 400


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
