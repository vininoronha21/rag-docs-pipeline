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
