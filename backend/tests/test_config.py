import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_default_embedding_dimensions_are_positive() -> None:
    settings = Settings(_env_file=None)

    assert settings.embedding_dimensions == 1536


def test_settings_reject_non_positive_embedding_dimensions() -> None:
    with pytest.raises(ValidationError):
        Settings(embedding_dimensions=0, _env_file=None)
