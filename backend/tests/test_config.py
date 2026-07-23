import pytest
from pydantic import ValidationError

from app.core.config import Settings

PRODUCTION_SETTINGS = {
    "environment": "production",
    "admin_secret": "production-secret",
    "database_url": "postgresql+asyncpg://user:pass@db.example.com:5432/rag?ssl=require",
    "migration_database_url": "postgresql+psycopg://user:pass@db.example.com:5432/rag?sslmode=require",
}


def test_settings_default_embedding_dimensions_are_positive() -> None:
    settings = Settings(_env_file=None)

    assert settings.embedding_dimensions == 1536


def test_settings_reject_non_positive_embedding_dimensions() -> None:
    with pytest.raises(ValidationError):
        Settings(embedding_dimensions=0, _env_file=None)


def test_settings_reject_embedding_dimensions_that_do_not_match_pgvector_schema() -> None:
    with pytest.raises(ValidationError, match="EMBEDDING_DIMENSIONS must remain 1536"):
        Settings(embedding_dimensions=1024, _env_file=None)


def test_settings_http_hardening_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.http_timeout_seconds == 30.0
    assert settings.http_max_retries == 2
    assert settings.http_retry_backoff_seconds == 0.5


def test_settings_reject_negative_http_retries() -> None:
    with pytest.raises(ValidationError):
        Settings(http_max_retries=-1, _env_file=None)


def test_settings_reject_non_positive_http_timeout() -> None:
    with pytest.raises(ValidationError):
        Settings(http_timeout_seconds=0, _env_file=None)


def test_settings_hybrid_retrieval_defaults_are_valid() -> None:
    settings = Settings(_env_file=None)

    assert settings.retrieval_candidate_k > 12
    assert settings.retrieval_rrf_k > 0
    assert settings.retrieval_vector_weight > 0
    assert settings.retrieval_text_weight > 0
    assert settings.retrieval_min_fused_score >= 0
    assert settings.retrieval_min_score_gap >= 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("retrieval_candidate_k", 12),
        ("retrieval_rrf_k", 0),
        ("retrieval_vector_weight", 0),
        ("retrieval_vector_weight", -0.1),
        ("retrieval_text_weight", 0),
        ("retrieval_text_weight", -0.1),
        ("retrieval_min_fused_score", -0.1),
        ("retrieval_min_score_gap", -0.1),
    ],
)
def test_settings_reject_invalid_hybrid_retrieval_values(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value}, _env_file=None)


def test_production_requires_explicit_allowed_origins() -> None:
    with pytest.raises(ValidationError, match="ALLOWED_ORIGINS must be set"):
        Settings(**PRODUCTION_SETTINGS, _env_file=None)


@pytest.mark.parametrize(
    "origin",
    ["*", "http://localhost:3000", "http://127.0.0.1:3000"],
)
def test_production_rejects_wildcard_and_local_allowed_origins(origin: str) -> None:
    with pytest.raises(ValidationError, match="ALLOWED_ORIGINS"):
        Settings(**PRODUCTION_SETTINGS, allowed_origins=[origin], _env_file=None)


def test_production_rejects_empty_allowed_origins() -> None:
    with pytest.raises(ValidationError, match="ALLOWED_ORIGINS"):
        Settings(**PRODUCTION_SETTINGS, allowed_origins=[], _env_file=None)


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "https://docs.example.com/path",
        "https://docs.example.com?preview=1",
        "http://[::1]:3000",
        "http://localhost.:3000",
        "https://*.example.com",
        "https://user:pass@example.com",
        "https://example.com:bad",
        "https://example.com:",
        "http://app.localhost:3000",
    ],
)
def test_production_rejects_invalid_allowed_origin_shapes(origin: str) -> None:
    with pytest.raises(ValidationError, match="ALLOWED_ORIGINS"):
        Settings(**PRODUCTION_SETTINGS, allowed_origins=[origin], _env_file=None)


def test_production_accepts_explicit_https_allowed_origin() -> None:
    settings = Settings(
        **PRODUCTION_SETTINGS,
        allowed_origins=["https://docs.example.com"],
        _env_file=None,
    )

    assert settings.allowed_origins == ["https://docs.example.com"]
