import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize("environment", ["local", "test"])
def test_settings_allows_empty_admin_secret_outside_production(environment: str) -> None:
    settings = Settings(environment=environment, admin_secret="", _env_file=None)

    assert settings.admin_secret == ""


def test_settings_rejects_empty_admin_secret_for_production() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", admin_secret="", _env_file=None)
