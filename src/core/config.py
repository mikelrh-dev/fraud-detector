"""Application configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = "change-me-in-production"
    environment: str = "development"

    # Database
    db_user: str = "fraud"
    db_password: str = "fraud_secret"
    db_name: str = "fraud_detector"
    db_host: str = "localhost"
    db_port: int = 5432

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Ollama
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_exp_minutes: int = 15

    # Ensemble Weights
    ensemble_rule_weight: float = 0.45
    ensemble_ml_weight: float = 0.45
    ensemble_context_weight: float = 0.10

    # Threshold Tiers
    threshold_tiers: list[dict] = [
        {"min_amount": 0, "max_amount": 1000, "threshold": 70, "label": "low"},
        {"min_amount": 1001, "max_amount": 10000, "threshold": 60, "label": "medium"},
        {"min_amount": 10001, "max_amount": 50000, "threshold": 50, "label": "high"},
        {"min_amount": 50001, "max_amount": float("inf"), "threshold": 40, "label": "critical"},
    ]

    # Ollama
    ollama_timeout: int = 30

    # Feature Flags
    fraud_detection_enabled: bool = True

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

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
