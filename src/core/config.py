"""Application configuration."""

import math
import secrets

from pydantic import AliasChoices, Field
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
    # ENVIRONMENT is the canonical name. API_ENV is accepted as an alias because
    # it shipped in .env.example and in operator runbooks; without the alias the
    # whole production branch below was unreachable and a deployment that set
    # API_ENV=production silently ran with dev secrets, open CORS and public docs.
    environment: str = Field(
        "development",
        validation_alias=AliasChoices("ENVIRONMENT", "API_ENV"),
    )

    # Database
    db_user: str = "fraud"
    db_password: str  # No default — must be injected via env (security)
    db_name: str = "fraud_detector"
    db_host: str = "localhost"
    db_port: int = 5432

    # Redis
    redis_password: str  # No default — must be injected via env (security)
    redis_url: str  # No default — must be injected via env (security)

    # Ollama
    ollama_host: str = "http://localhost:11434"
    # Must match the model actually pulled in the Ollama container. Nothing in
    # the compose stack pulls it: the healthcheck runs `ollama list`, which
    # passes with zero models, so a clean deploy reports healthy and then 404s
    # on the first report. Changing this string does not install anything.
    ollama_model: str = "llama3.2:1b"

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

    # Threshold Tiers (half-open intervals [min, max) to avoid boundary gaps)
    threshold_tiers: list[dict] = [
        {"min_amount": 0, "max_amount": 1000.01, "threshold": 70, "label": "low"},
        {
            "min_amount": 1000.01,
            "max_amount": 10000.01,
            "threshold": 50,
            "label": "medium",
        },
        {
            "min_amount": 10000.01,
            "max_amount": 50000.01,
            "threshold": 45,
            "label": "high",
        },
        {
            "min_amount": 50000.01,
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

    # Risky merchants the rule engine treats as inherently adversarial
    # (rule_engine.py fires `unusual_merchant`, +20, on an exact
    # case-insensitive match against merchant_name).
    #
    # These were three string literals inlined in the request path
    # (api/v1/transactions.py), so extending the list needed a code change and
    # a deploy. They are additive, not load-bearing: the same rule also fires on
    # a merchant_category in MERCHANT_ADVERSARIAL_CATEGORIES, so an operator
    # emptying this list narrows the merchant-name signal without silencing
    # the rule.
    #
    # Override with a JSON array, as pydantic-settings expects for complex
    # types (same convention as threshold_tiers below):
    #   MERCHANT_BLACKLIST='["foo","bar"]'
    merchant_blacklist: list[str] = [
        "crypto exchange pro",
        "online gambling",
        "money transfer now",
    ]

    # Frontend
    frontend_url: str = "http://localhost:3000"

    # Proxy
    # Trust X-Real-IP / X-Forwarded-For headers for client identity.
    # Enable ONLY behind a trusted reverse proxy (nginx, ALB, Cloudflare).
    # X-Real-IP is preferred (single-value, set by proxy); X-Forwarded-For
    # leftmost is used as fallback.
    # When False (default), request.client.host is used directly — spoof-proof.
    trust_proxy_headers: bool = False

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
