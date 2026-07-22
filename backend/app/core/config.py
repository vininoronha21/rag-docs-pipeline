from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

DEFAULT_DATABASE_URL = "postgresql+asyncpg://rag:rag@localhost:5432/rag_docs"
DEFAULT_MIGRATION_DATABASE_URL = "postgresql+psycopg://rag:rag@localhost:5432/rag_docs"


def _validate_database_driver(env_name: str, database_url: str, expected_driver: str) -> None:
    try:
        drivername = make_url(database_url).drivername
    except ArgumentError as exc:
        raise ValueError(f"{env_name} must be a valid SQLAlchemy database URL.") from exc

    if drivername != expected_driver:
        raise ValueError(f"{env_name} must use the {expected_driver} SQLAlchemy driver.")


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
        _validate_database_driver("DATABASE_URL", self.database_url, "postgresql+asyncpg")
        _validate_database_driver(
            "MIGRATION_DATABASE_URL",
            self.migration_database_url,
            "postgresql+psycopg",
        )

        if self.environment == "production" and not self.admin_secret.strip():
            raise ValueError("ADMIN_SECRET must be set when ENVIRONMENT=production.")
        if self.environment == "production":
            missing = [
                env_name
                for field_name, env_name in (
                    ("database_url", "DATABASE_URL"),
                    ("migration_database_url", "MIGRATION_DATABASE_URL"),
                )
                if field_name not in self.model_fields_set
            ]
            if missing:
                raise ValueError(
                    f"{', '.join(missing)} must be set when ENVIRONMENT=production."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
