import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text

from . import conftest as integration_conftest


@pytest.mark.integration
def test_alembic_test_environment_uses_sync_migration_url_and_async_runtime_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_database_url = "postgresql+psycopg://rag:rag@localhost:5432/rag_docs_test"
    observed_env: list[tuple[str | None, str | None]] = []

    class _StopFixture(Exception):
        pass

    class _FakeEngine:
        def connect(self) -> None:
            raise AssertionError("fixture should stop before opening a DB connection")

        def dispose(self) -> None:
            pass

    def fake_create_engine(database_url: str) -> _FakeEngine:
        assert database_url == test_database_url
        return _FakeEngine()

    def fake_downgrade(_config: Config, _revision: str) -> None:
        observed_env.append(
            (
                os.environ.get("DATABASE_URL"),
                os.environ.get("MIGRATION_DATABASE_URL"),
            )
        )
        raise _StopFixture

    monkeypatch.setenv("TEST_DATABASE_URL", test_database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    monkeypatch.setattr(integration_conftest, "create_engine", fake_create_engine)
    monkeypatch.setattr(integration_conftest.command, "downgrade", fake_downgrade)

    with pytest.raises(_StopFixture):
        next(integration_conftest.sync_connection.__wrapped__())

    assert observed_env == [
        (
            "postgresql+asyncpg://rag:rag@localhost:5432/rag_docs_test",
            test_database_url,
        )
    ]


@pytest.mark.integration
def test_schema_has_vector_extension_and_hnsw(sync_connection: Connection) -> None:
    extension = sync_connection.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    ).scalar_one()
    index = tuple(
        sync_connection.execute(
            text(
                "SELECT access_method.amname, table_relation.relname, "
                "indexed_column.attname, operator_class.opcname "
                "FROM pg_class AS index_relation "
                "JOIN pg_namespace AS index_namespace "
                "ON index_namespace.oid = index_relation.relnamespace "
                "JOIN pg_index AS index_metadata "
                "ON index_metadata.indexrelid = index_relation.oid "
                "JOIN pg_am AS access_method "
                "ON access_method.oid = index_relation.relam "
                "JOIN pg_class AS table_relation "
                "ON table_relation.oid = index_metadata.indrelid "
                "JOIN pg_attribute AS indexed_column "
                "ON indexed_column.attrelid = table_relation.oid "
                "AND indexed_column.attnum = index_metadata.indkey[0] "
                "JOIN pg_opclass AS operator_class "
                "ON operator_class.oid = index_metadata.indclass[0] "
                "WHERE index_relation.relname = "
                "'ix_document_chunks_embedding_hnsw' "
                "AND index_namespace.nspname = current_schema()"
            )
        ).one()
    )

    assert extension == "vector"
    assert index == ("hnsw", "document_chunks", "embedding", "vector_cosine_ops")


@pytest.mark.integration
def test_schema_has_stored_portuguese_search_vector_and_gin_index(
    sync_connection: Connection,
) -> None:
    generated_column = tuple(
        sync_connection.execute(
            text(
                "SELECT data_type, is_generated, generation_expression "
                "FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = 'document_chunks' AND column_name = 'search_vector'"
            )
        ).one()
    )
    index = tuple(
        sync_connection.execute(
            text(
                "SELECT access_method.amname, table_relation.relname, indexed_column.attname "
                "FROM pg_class AS index_relation "
                "JOIN pg_namespace AS index_namespace "
                "ON index_namespace.oid = index_relation.relnamespace "
                "JOIN pg_index AS index_metadata "
                "ON index_metadata.indexrelid = index_relation.oid "
                "JOIN pg_am AS access_method ON access_method.oid = index_relation.relam "
                "JOIN pg_class AS table_relation "
                "ON table_relation.oid = index_metadata.indrelid "
                "JOIN pg_attribute AS indexed_column "
                "ON indexed_column.attrelid = table_relation.oid "
                "AND indexed_column.attnum = index_metadata.indkey[0] "
                "WHERE index_relation.relname = 'ix_document_chunks_search_vector_gin' "
                "AND index_namespace.nspname = current_schema()"
            )
        ).one()
    )

    assert generated_column[0:2] == ("tsvector", "ALWAYS")
    assert generated_column[2].replace(" ", "") == (
        "to_tsvector('portuguese'::regconfig,COALESCE(chunk_text,''::text))"
    )
    assert index == ("gin", "document_chunks", "search_vector")


@pytest.mark.integration
def test_hybrid_search_migration_downgrade_restores_empty_legacy_queries_schema(
    sync_connection: Connection,
) -> None:
    sync_connection.execute(
        text(
            "INSERT INTO query_events "
            "(state, latency_ms, retrieved_chunk_count, source_ids, source_version_ids) "
            "VALUES ('answered', 12, 2, ARRAY[1], ARRAY[2])"
        )
    )
    sync_connection.commit()

    backend_dir = Path(__file__).resolve().parents[2]
    alembic_config = Config(backend_dir / "alembic.ini")
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))

    with integration_conftest._alembic_test_database_environment(
        os.environ["TEST_DATABASE_URL"]
    ):
        try:
            command.downgrade(alembic_config, "202607130001")

            legacy_columns = set(
                sync_connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = current_schema() AND table_name = 'queries'"
                    )
                ).scalars()
            )
            query_count = sync_connection.execute(
                text("SELECT count(*) FROM queries")
            ).scalar_one()
            query_events_table = sync_connection.execute(
                text("SELECT to_regclass('query_events')")
            ).scalar_one()
            search_vector_column = sync_connection.execute(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = 'document_chunks' AND column_name = 'search_vector'"
                )
            ).scalar_one()
            sync_connection.rollback()

            assert legacy_columns == {
                "id",
                "user_query",
                "retrieved_chunks_ids",
                "llm_response",
                "user_feedback",
                "latency_ms",
                "retrieved_chunk_count",
                "created_at",
            }
            assert query_count == 0
            assert query_events_table is None
            assert search_vector_column == 0
        finally:
            sync_connection.rollback()
            command.upgrade(alembic_config, "head")


@pytest.mark.integration
def test_source_version_downgrade_destroys_documents_and_restores_legacy_unique_url(
    sync_connection: Connection,
) -> None:
    source_id = sync_connection.execute(
        text(
            "INSERT INTO doc_sources "
            "(source_type, source_config, enabled, repository, branch, path, language) "
            "VALUES ('github', '{}', true, 'downgrade/project', 'main', 'docs', 'pt-BR') "
            "RETURNING id"
        )
    ).scalar_one()
    version_id = sync_connection.execute(
        text(
            "INSERT INTO source_versions "
            "(source_id, commit_sha, embedding_provider, embedding_model, "
            "embedding_dimensions, document_count, chunk_count) "
            "VALUES (:source_id, :commit_sha, 'local', 'hash', 1536, 1, 0) "
            "RETURNING id"
        ),
        {"source_id": source_id, "commit_sha": "d" * 40},
    ).scalar_one()
    sync_connection.execute(
        text(
            "INSERT INTO documents "
            "(source_version_id, repository_path, source, source_url, content) "
            "VALUES (:version_id, 'docs/downgrade.md', 'github', "
            "'https://example.test/downgrade', 'content')"
        ),
        {"version_id": version_id},
    )
    sync_connection.commit()

    backend_dir = Path(__file__).resolve().parents[2]
    alembic_config = Config(backend_dir / "alembic.ini")
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))

    with integration_conftest._alembic_test_database_environment(
        os.environ["TEST_DATABASE_URL"]
    ):
        try:
            command.downgrade(alembic_config, "202606170002")

            document_count = sync_connection.execute(
                text("SELECT count(*) FROM documents")
            ).scalar_one()
            source_url_constraints = (
                sync_connection.execute(
                    text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                        "WHERE conrelid = 'documents'::regclass AND contype = 'u'"
                    )
                )
                .scalars()
                .all()
            )
            source_versions_table = sync_connection.execute(
                text("SELECT to_regclass('source_versions')")
            ).scalar_one()
            legacy_column = sync_connection.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = 'documents' AND column_name = 'doc_source_id'"
                )
            ).scalar_one()
            legacy_index = sync_connection.execute(
                text("SELECT to_regclass('ix_documents_doc_source_id')")
            ).scalar_one()
            legacy_fk = sync_connection.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname = 'fk_documents_doc_source_id_doc_sources'"
                )
            ).scalar_one()
            sync_connection.rollback()

            assert document_count == 0
            assert source_url_constraints == ["UNIQUE (source_url)"]
            assert source_versions_table is None
            assert legacy_column == "YES"
            assert legacy_index == "ix_documents_doc_source_id"
            assert legacy_fk == (
                "FOREIGN KEY (doc_source_id) REFERENCES doc_sources(id) ON DELETE SET NULL"
            )
        finally:
            sync_connection.rollback()
            command.upgrade(alembic_config, "head")
