import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text


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
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

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
        try:
            command.upgrade(alembic_config, "head")
        finally:
            if previous_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_database_url
