import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_default_embedding_dimensions_are_positive() -> None:
    settings = Settings(_env_file=None)

    assert settings.embedding_dimensions == 1536


def test_settings_reject_non_positive_embedding_dimensions() -> None:
    with pytest.raises(ValidationError):
        Settings(embedding_dimensions=0, _env_file=None)


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
