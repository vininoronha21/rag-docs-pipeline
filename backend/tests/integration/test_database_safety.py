import pytest

from . import conftest


def _validator():
    validator = getattr(conftest, "_validate_test_database_url", None)
    assert validator is not None, "database safety validator is missing"
    return validator


def test_rejects_normalized_development_database_without_exposing_credentials() -> None:
    secret = "development-secret"
    development_url = f"postgresql+asyncpg://rag:{secret}@localhost:5432/rag_docs"
    test_url = f"postgresql+psycopg://rag:{secret}@localhost:5432/rag_docs"

    with pytest.raises(pytest.UsageError, match="development database") as exc_info:
        _validator()(test_url, development_url)

    assert secret not in str(exc_info.value)


def test_rejects_database_without_test_suffix() -> None:
    with pytest.raises(pytest.UsageError, match="_test"):
        _validator()(
            "postgresql+psycopg://rag:secret@localhost:5432/rag_docs_staging",
            "postgresql+asyncpg://rag:secret@localhost:5432/rag_docs",
        )


def test_rejects_non_postgresql_database() -> None:
    with pytest.raises(pytest.UsageError, match="PostgreSQL"):
        _validator()(
            "sqlite:///rag_docs_test",
            "postgresql+asyncpg://rag:secret@localhost:5432/rag_docs",
        )


def test_accepts_disposable_test_database() -> None:
    _validator()(
        "postgresql+psycopg://rag:secret@localhost:5432/rag_docs_test",
        "postgresql+asyncpg://rag:secret@localhost:5432/rag_docs",
    )
