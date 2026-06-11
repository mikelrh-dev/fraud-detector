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
