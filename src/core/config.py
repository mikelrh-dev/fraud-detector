"""Application configuration."""

import math
import secrets

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# The signing secrets production must be given, keyed by field name.
#
# The env-var name is what an operator types, so it is what belongs in the error
# message: the previous wording named the Python fields (`jwt_secret_key`), which
# is a second lookup away from the variable actually missing from the box.
_REQUIRED_PRODUCTION_SECRETS = {
    "jwt_secret_key": "JWT_SECRET_KEY",
    "api_secret_key": "API_SECRET_KEY",
}

_GENERATE_SECRET_HINT = (
    'Generate each with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
)

# Values that are a placeholder wearing a secret's shape.
#
# Two tiers, because the cost of each mistake differs. The exact set only
# rejects a value that IS the placeholder: `JWT_SECRET_KEY=secret` is not a
# secret, and no real secret equals "secret" either, so the comparison cannot
# misfire on generated material. The substring tier exists for the values that
# embed a placeholder inside something longer — `change_me_in_production` is the
# literal value shipped in `.env.example`.
#
# False positives are the risk worth naming: a real secret is
# `secrets.token_urlsafe(32)`, 43 characters drawn from [A-Za-z0-9_-], so the
# shortest marker below ("insecure", 7 chars) appearing inside one has a
# probability around 1e-11. A minimum-length rule would catch far more
# placeholders, but that is an operator policy this guard was not asked to make;
# it stays a deliberate omission until someone decides the policy rather than
# inheriting it from a length heuristic.
_PLACEHOLDER_SECRETS_EXACT = frozenset(
    {
        "secret",
        "secretkey",
        "secretkeyhere",
        "password",
        "pass",
        "key",
        "example",
        "examplekey",
        "examplekey123",
        "supersecret",
        "jwtsecret",
        "jwtsecretkey",
        "apisecret",
        "apisecretkey",
        "todo",
        "fixme",
        "none",
        "null",
        "nil",
        "default",
        "test",
        "dev",
        "development",
        "local",
        "debug",
    }
)

_PLACEHOLDER_SECRETS_SUBSTRINGS = (
    "changeme",
    "replaceme",
    "yoursecret",
    "placeholder",
    "insecure",
    "notasecret",
    "dummysecret",
    "devsecret",
    "localsecret",
    "testsecret",
    "samplekey",
    "examplekey",
    "donotuse",
    "donotcommit",
    "mustchange",
)


def _is_placeholder_secret(value: str) -> bool:
    """Is this secret missing in everything but name?

    Empty and whitespace-only count: `JWT_SECRET_KEY=` is what `.env.example`
    ships, and a shell heredoc that fails to expand a variable leaves the same
    thing behind. Comparing after stripping case and the separators an operator
    reflexively sprinkles through a placeholder (`change-me`, `change_me`,
    `Change Me`) collapses those variants onto one value.
    """
    if not value.strip():
        return True
    normalized = "".join(c for c in value.lower() if c not in "-_ \t\r\n")
    if normalized in _PLACEHOLDER_SECRETS_EXACT:
        return True
    return any(marker in normalized for marker in _PLACEHOLDER_SECRETS_SUBSTRINGS)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def _check_production_secrets(self) -> None:
        """R1-005: production must inject real secrets explicitly via env.

        Dev defaults are ephemeral random values; in production they would
        silently differ between workers and rotate on every restart.

        Two failures are distinguished, because they are two different problems
        with two different fixes:

        * **absent** — the variable was never set, so the ephemeral default was
          used. Detected via `model_fields_set`.
        * **not a secret** — the variable WAS set, to nothing or to a
          placeholder. `model_fields_set` cannot see this: pydantic records the
          field as set the moment it assigns it, and an empty string is still
          an assignment. Measured, with `ENVIRONMENT=production` and
          `JWT_SECRET_KEY=`: booted, `jwt_secret_key` of length 0. An empty
          HMAC key is not a weak key, it is no key — anyone can mint a valid
          token. So presence is not checked here; the value is.
        """
        if self.environment != "production":
            return
        injected = set(_REQUIRED_PRODUCTION_SECRETS) & self.model_fields_set
        missing = set(_REQUIRED_PRODUCTION_SECRETS) - injected
        if missing:
            raise ValueError(
                "Production environment requires explicit env injection of: "
                + ", ".join(sorted(_REQUIRED_PRODUCTION_SECRETS[f] for f in missing))
                + ". "
                + _GENERATE_SECRET_HINT
            )

        placeholders = sorted(
            _REQUIRED_PRODUCTION_SECRETS[field]
            for field, var_name in _REQUIRED_PRODUCTION_SECRETS.items()
            if _is_placeholder_secret(getattr(self, field))
        )
        if placeholders:
            raise ValueError(
                "Production refused to boot: "
                + ", ".join(placeholders)
                + " is empty or a placeholder, which is not a signing key. "
                + _GENERATE_SECRET_HINT
                + ". Development keeps its ephemeral default; this check is "
                "production-only."
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

    # ML agreement floor for the rule branch of the routed policy.
    #
    # `_classify_routed` blocks on rule evidence ALONE only when
    # `rule_score > threshold AND amount >= critical_floor`. Without a condition
    # on the model, that branch could override the model asserting the
    # transaction was ordinary: measured, `acme`/`retail` at 50,001 EUR scores
    # rule 48.59 against a threshold of 40 and ml 0.13, and the rules alone
    # blocked it.
    #
    # 5.0 is not a confidence bar, it is a "has the model spoken" bar. 5 out of
    # 100 is a very weak signal and it is enough; anything below it is the model
    # reporting that it found nothing, and blocking over that is a block on the
    # rules' authority alone.
    #
    # It gates the RULE branch only. `ml > threshold` alone still blocks, because
    # that is the model overruling the rules and this floor exists precisely to
    # discount a model with nothing to say. It also does not touch the degraded
    # path: with no model there is nothing to agree with, and the shipped
    # ensemble decides.
    #
    # FRAGILITY: the flagship rule-driven fraud (400k USD to `binance` at 03:00)
    # scores ml 17.96 and so clears this by 12.96. A retrain that pulled that
    # score under 5.0 would silently downgrade it to `review`.
    # `TestTheRuleBranchNeedsTheModelToAgree.test_case_a_clears_the_floor_with_margin`
    # pins the margin so the retrain fails the suite instead of the case.
    #
    # Bounded to the [0, 100] score scale, because the field used to accept
    # anything and both ends outside that scale fail SILENTLY rather than
    # loudly:
    #   * `<= 0` makes `ml_score >= floor` true for every transaction, including
    #     one the model is actively calling ordinary — that is the pre-floor
    #     rule-only blocking this gate exists to prevent, back with no log.
    #   * `> 100` (or `inf`) makes the gate unreachable, disabling the amount
    #     policy on the rule branch for good.
    # Both are operator-typed env values, so they must fail at boot where the
    # mistake is visible instead of at the first scored transaction. The bound
    # is inclusive: 0.0 ("the model only has to have run") and 100.0 ("only a
    # maximal score agrees") are legitimate configurations, not typos.
    ml_floor: float = Field(5.0, ge=0.0, le=100.0)

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
