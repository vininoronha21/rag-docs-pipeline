import pytest
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
