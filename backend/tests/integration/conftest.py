import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine

from app.core.config import get_settings


@pytest.fixture(scope="session")
def sync_connection() -> Iterator[Connection]:
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        raise pytest.UsageError("TEST_DATABASE_URL is required for integration tests")

    backend_dir = Path(__file__).resolve().parents[2]
    alembic_config = Config(backend_dir / "alembic.ini")
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))
    engine = create_engine(test_database_url)

    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_database_url
    get_settings.cache_clear()

    try:
        command.downgrade(alembic_config, "base")
        command.upgrade(alembic_config, "head")
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        get_settings.cache_clear()

    try:
        with engine.connect() as connection:
            yield connection
    finally:
        engine.dispose()
