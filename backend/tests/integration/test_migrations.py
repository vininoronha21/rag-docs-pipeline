import pytest
from sqlalchemy import Connection, text


@pytest.mark.integration
def test_schema_has_vector_extension_and_hnsw(sync_connection: Connection) -> None:
    extension = sync_connection.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    ).scalar_one()
    index = sync_connection.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE indexname = 'ix_document_chunks_embedding_hnsw'"
        )
    ).scalar_one()

    assert extension == "vector"
    assert index == "ix_document_chunks_embedding_hnsw"
