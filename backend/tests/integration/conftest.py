import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

from app.core.config import Settings, get_settings


def _parse_postgresql_url(database_url: str) -> URL:
    try:
        url = make_url(database_url)
    except ArgumentError:
        raise pytest.UsageError("Database URL must be a valid PostgreSQL URL") from None

    if url.get_backend_name() != "postgresql":
        raise pytest.UsageError("Database URL must target PostgreSQL")
    return url


def _database_identity(url: URL) -> tuple[str, int, str | None]:
    return ((url.host or "localhost").casefold(), url.port or 5432, url.database)


def _validate_test_database_url(
    test_database_url: str, development_database_url: str
) -> None:
    test_url = _parse_postgresql_url(test_database_url)
    development_url = _parse_postgresql_url(development_database_url)

    if _database_identity(test_url) == _database_identity(development_url):
        raise pytest.UsageError("TEST_DATABASE_URL must not target the development database")
    if not test_url.database or not test_url.database.endswith("_test"):
        raise pytest.UsageError("TEST_DATABASE_URL database name must end with '_test'")


def _async_runtime_url_for_test_database(test_database_url: str) -> str:
    url = _parse_postgresql_url(test_database_url)
    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    if sslmode is not None and "ssl" not in query:
        query["ssl"] = sslmode
    return (
        url.set(drivername="postgresql+asyncpg", query=query)
        .render_as_string(hide_password=False)
    )


@contextmanager
def _alembic_test_database_environment(test_database_url: str) -> Iterator[None]:
    previous_database_url = os.environ.get("DATABASE_URL")
    previous_migration_database_url = os.environ.get("MIGRATION_DATABASE_URL")

    os.environ["DATABASE_URL"] = _async_runtime_url_for_test_database(test_database_url)
    os.environ["MIGRATION_DATABASE_URL"] = test_database_url
    get_settings.cache_clear()

    try:
        yield
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        if previous_migration_database_url is None:
            os.environ.pop("MIGRATION_DATABASE_URL", None)
        else:
            os.environ["MIGRATION_DATABASE_URL"] = previous_migration_database_url
        get_settings.cache_clear()


@pytest.fixture(scope="session")
def sync_connection() -> Iterator[Connection]:
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        raise pytest.UsageError("TEST_DATABASE_URL is required for integration tests")
    _validate_test_database_url(test_database_url, Settings().database_url)

    backend_dir = Path(__file__).resolve().parents[2]
    alembic_config = Config(backend_dir / "alembic.ini")
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))
    engine = create_engine(test_database_url)

    with _alembic_test_database_environment(test_database_url):
        command.downgrade(alembic_config, "base")
        command.upgrade(alembic_config, "head")

    try:
        with engine.connect() as connection:
            yield connection
    finally:
        engine.dispose()
