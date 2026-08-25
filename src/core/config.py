"""Application configuration."""

import math
import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def _check_production_secrets(self) -> None:
        """R1-005: production must inject secrets explicitly via env.

        Dev defaults are ephemeral random values; in production they would
        silently differ between workers and rotate on every restart.
        """
        if self.environment != "production":
            return
        injected = {"jwt_secret_key", "api_secret_key"} & self.model_fields_set
        missing = {"jwt_secret_key", "api_secret_key"} - injected
        if missing:
            raise ValueError(
                "Production environment requires explicit env injection of: "
                + ", ".join(sorted(missing))
            )

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._check_production_secrets()

    # API
    # pi-lens-ignore: S104
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Ephemeral dev secret; production MUST inject via env (R1-005 guard, wave 5).
    api_secret_key: str = secrets.token_urlsafe(32)
    environment: str = "development"

    # Database
    db_user: str = "fraud"
    # pi-lens-ignore: S105
    db_password: str = "fraud_secret"
    db_name: str = "fraud_detector"
    db_host: str = "localhost"
    db_port: int = 5432

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Ollama
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:0.5b"

    # JWT
    # Ephemeral dev secret; production MUST inject via env (R1-005 guard, wave 5).
    jwt_secret_key: str = secrets.token_urlsafe(32)
    jwt_algorithm: str = "HS256"
    jwt_exp_minutes: int = 15
    jwt_refresh_exp_minutes: int = 60 * 24  # refresh tokens live 24h

    # Ensemble Weights
    ensemble_rule_weight: float = 0.60
    ensemble_ml_weight: float = 0.25
    ensemble_context_weight: float = 0.15

    # Threshold Tiers
    threshold_tiers: list[dict] = [
        {"min_amount": 0, "max_amount": 1000, "threshold": 70, "label": "low"},
        {
            "min_amount": 1001,
            "max_amount": 10000,
            "threshold": 50,
            "label": "medium",
        },  # Lowered from 60
        {
            "min_amount": 10001,
            "max_amount": 50000,
            "threshold": 45,
            "label": "high",
        },  # Lowered from 50 for consistency
        {
            "min_amount": 50001,
            "max_amount": math.inf,
            "threshold": 40,
            "label": "critical",
        },
    ]

    # Ollama
    ollama_timeout: int = 30

    # Feature Flags
    fraud_detection_enabled: bool = True
    velocity_store_enabled: bool = True

    # Frontend
    frontend_url: str = "http://localhost:3000"

    @property
    def database_url(self) -> str:
        """Build async database URL."""
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def cors_origins(self) -> list[str]:
        """Return allowed CORS origins."""
        if self.environment == "production":
            return [self.frontend_url]
        return ["*"]


settings = Settings()
