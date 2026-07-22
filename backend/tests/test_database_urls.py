import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core import config as app_config
from app.core.config import Settings


def test_production_requires_explicit_runtime_and_migration_database_urls() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(environment="production", admin_secret="secret-for-tests", _env_file=None)

    with pytest.raises(ValidationError, match="MIGRATION_DATABASE_URL"):
        Settings(
            environment="production",
            admin_secret="secret-for-tests",
            database_url="postgresql+asyncpg://user:pass@host.example.com:5432/app",
            _env_file=None,
        )


def test_production_preserves_tls_query_parameters_on_both_database_urls() -> None:
    runtime_url = (
        "postgresql+asyncpg://user:pass@ep-runtime.neon.tech/app"
        "?sslmode=require&channel_binding=require"
    )
    migration_url = (
        "postgresql+psycopg://user:pass@ep-migration.neon.tech/app"
        "?sslmode=require&channel_binding=require"
    )

    settings = Settings(
        environment="production",
        admin_secret="secret-for-tests",
        database_url=runtime_url,
        migration_database_url=migration_url,
        _env_file=None,
    )

    assert settings.database_url == runtime_url
    assert settings.migration_database_url == migration_url


def test_runtime_database_url_rejects_sync_driver() -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+asyncpg"):
        Settings(
            database_url="postgresql+psycopg://user:pass@localhost:5432/rag_docs",
            _env_file=None,
        )


def test_migration_database_url_rejects_async_driver() -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+psycopg"):
        Settings(
            migration_database_url="postgresql+asyncpg://user:pass@localhost:5432/rag_docs",
            _env_file=None,
        )


def test_alembic_uses_migration_database_url_without_deriving_from_runtime_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_url = (
        "postgresql+asyncpg://runtime:pass@ep-runtime.neon.tech/runtime_db"
        "?sslmode=require&channel_binding=require"
    )
    migration_url = (
        "postgresql+psycopg://migration:pass@ep-migration.neon.tech/migration_db"
        "?sslmode=require&channel_binding=require"
    )
    recorded_options: dict[str, str] = {}

    class _StopImport(Exception):
        pass

    class _FakeConfig:
        config_file_name = None
        config_ini_section = "alembic"

        def set_main_option(self, key: str, value: str) -> None:
            recorded_options[key] = value

        def get_main_option(self, key: str) -> str:
            return recorded_options[key]

        def get_section(self, _name: str, _default: object) -> dict[str, str]:
            return {}

    fake_context = SimpleNamespace(
        config=_FakeConfig(),
        is_offline_mode=lambda: (_ for _ in ()).throw(_StopImport()),
    )
    fake_alembic = types.ModuleType("alembic")
    fake_alembic.context = fake_context

    monkeypatch.setattr(
        app_config,
        "get_settings",
        lambda: SimpleNamespace(
            database_url=runtime_url,
            migration_database_url=migration_url,
            embedding_dimensions=1536,
        ),
    )
    monkeypatch.setitem(sys.modules, "alembic", fake_alembic)

    env_path = Path(__file__).resolve().parents[1] / "alembic" / "env.py"
    spec = importlib.util.spec_from_file_location("test_alembic_env_database_url", env_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None

    with pytest.raises(_StopImport):
        spec.loader.exec_module(module)

    assert recorded_options["sqlalchemy.url"] == migration_url
