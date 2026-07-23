from functools import lru_cache
from ipaddress import ip_address
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, HttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

DEFAULT_DATABASE_URL = "postgresql+asyncpg://rag:rag@localhost:5432/rag_docs"
DEFAULT_MIGRATION_DATABASE_URL = "postgresql+psycopg://rag:rag@localhost:5432/rag_docs"
FORBIDDEN_ASYNCPG_RUNTIME_QUERY_KEYS = frozenset({"channel_binding", "sslmode"})
PGVECTOR_EMBEDDING_DIMENSIONS = 1536


def _validate_database_driver(
    env_name: str, database_url: str, expected_driver: str
) -> URL:
    try:
        parsed_url = make_url(database_url)
    except ArgumentError as exc:
        raise ValueError(f"{env_name} must be a valid SQLAlchemy database URL.") from exc

    if parsed_url.drivername != expected_driver:
        raise ValueError(f"{env_name} must use the {expected_driver} SQLAlchemy driver.")
    return parsed_url


def _validate_asyncpg_runtime_query_parameters(database_url: URL) -> None:
    unsupported_keys = sorted(
        FORBIDDEN_ASYNCPG_RUNTIME_QUERY_KEYS.intersection(database_url.query)
    )
    if unsupported_keys:
        unsupported = ", ".join(unsupported_keys)
        raise ValueError(
            "DATABASE_URL uses asyncpg; use the asyncpg TLS query parameter "
            f"ssl instead of unsupported parameter(s): {unsupported}."
        )


def _validate_production_allowed_origins(allowed_origins: list[str]) -> None:
    if not allowed_origins:
        raise ValueError("ALLOWED_ORIGINS must include at least one production origin.")

    for origin in allowed_origins:
        parsed = urlparse(origin.strip())
        if (
            not origin.strip()
            or origin != origin.strip()
            or not parsed.scheme
            or not parsed.netloc
            or parsed.path
            or parsed.params
            or parsed.query
            or parsed.fragment
            or parsed.hostname is None
        ):
            raise ValueError(
                "ALLOWED_ORIGINS must contain exact origins without paths, "
                "queries, or fragments when ENVIRONMENT=production."
            )

        if origin.strip() == "*" or _is_loopback_hostname(parsed.hostname):
            raise ValueError(
                "ALLOWED_ORIGINS must not include wildcard or localhost origins "
                "when ENVIRONMENT=production."
            )


def _is_loopback_hostname(hostname: str) -> bool:
    if hostname.lower() == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RAG Docs Pipeline"
    environment: Literal["local", "test", "production"] = "local"
    api_prefix: str = "/api"
    admin_secret: str = Field(default="", repr=False)
    query_rate_limit_per_minute: int = Field(default=20, gt=0)
    feedback_rate_limit_per_minute: int = Field(default=30, gt=0)
    sync_rate_limit_per_minute: int = Field(default=2, gt=0)

    database_url: str = Field(
        default=DEFAULT_DATABASE_URL,
        description="Async SQLAlchemy database URL.",
    )
    migration_database_url: str = Field(
        default=DEFAULT_MIGRATION_DATABASE_URL,
        description="Sync SQLAlchemy database URL for Alembic migrations.",
    )

    github_token: str | None = None
    github_user_agent: str = "rag-docs-pipeline"

    http_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Connection/read timeout for external HTTP calls (GitHub, OpenAI).",
    )
    http_max_retries: int = Field(
        default=2,
        ge=0,
        description="Retry attempts for transient external HTTP failures (429/5xx/network).",
    )
    http_retry_backoff_seconds: float = Field(
        default=0.5,
        ge=0,
        description="Base seconds for exponential backoff between HTTP retries.",
    )

    embedding_provider: Literal["local", "openai"] = "local"
    embedding_dimensions: int = Field(
        default=1536,
        ge=1,
        description="Embedding vector dimensions used by providers and pgvector columns.",
    )
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"

    llm_provider: Literal["extractive", "openai"] = "extractive"
    openai_chat_model: str = "gpt-4.1-mini"
    retrieval_min_score: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
        description="Minimum pgvector cosine similarity score required before answering.",
    )
    retrieval_min_fused_score: float = Field(
        default=0.0,
        ge=0.0,
        description="Minimum leading reciprocal-rank-fusion score required to answer.",
    )
    retrieval_min_score_gap: float = Field(
        default=0.0,
        ge=0.0,
        description="Minimum fused-score gap from the second result when one exists.",
    )
    retrieval_candidate_k: int = Field(
        default=50,
        gt=12,
        description="Candidates collected per retrieval arm; must exceed the maximum top_k.",
    )
    retrieval_rrf_k: int = Field(default=60, gt=0)
    retrieval_vector_weight: float = Field(default=0.7, gt=0)
    retrieval_text_weight: float = Field(default=0.3, gt=0)

    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    public_backend_url: HttpUrl | None = None

    @model_validator(mode="after")
    def validate_deployment_settings(self) -> "Settings":
        runtime_url = _validate_database_driver(
            "DATABASE_URL", self.database_url, "postgresql+asyncpg"
        )
        _validate_asyncpg_runtime_query_parameters(runtime_url)
        _validate_database_driver(
            "MIGRATION_DATABASE_URL",
            self.migration_database_url,
            "postgresql+psycopg",
        )

        if self.embedding_dimensions != PGVECTOR_EMBEDDING_DIMENSIONS:
            raise ValueError(
                "EMBEDDING_DIMENSIONS must remain 1536 for the current pgvector schema."
            )

        if self.environment == "production" and not self.admin_secret.strip():
            raise ValueError("ADMIN_SECRET must be set when ENVIRONMENT=production.")
        if self.environment == "production":
            missing = [
                env_name
                for field_name, env_name in (
                    ("database_url", "DATABASE_URL"),
                    ("migration_database_url", "MIGRATION_DATABASE_URL"),
                    ("allowed_origins", "ALLOWED_ORIGINS"),
                )
                if field_name not in self.model_fields_set
            ]
            if missing:
                raise ValueError(
                    f"{', '.join(missing)} must be set when ENVIRONMENT=production."
                )
            _validate_production_allowed_origins(self.allowed_origins)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
