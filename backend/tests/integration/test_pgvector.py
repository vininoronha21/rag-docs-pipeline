import pytest
from sqlalchemy import Connection, text


@pytest.mark.integration
def test_cosine_query_ranks_identical_vector_first(sync_connection: Connection) -> None:
    document_id = sync_connection.execute(
        text(
            "INSERT INTO documents (source, source_url, title, content) "
            "VALUES (:source, :source_url, :title, :content) RETURNING id"
        ),
        {
            "source": "integration-test",
            "source_url": "https://example.com/integration-test",
            "title": "Integration test",
            "content": "Cosine distance fixture",
        },
    ).scalar_one()

    identical_vector = "[" + ",".join(["1"] + ["0"] * 1535) + "]"
    different_vector = "[" + ",".join(["0", "1"] + ["0"] * 1534) + "]"
    sync_connection.execute(
        text(
            "INSERT INTO document_chunks "
            "(document_id, chunk_text, chunk_index, chunk_hash, embedding) VALUES "
            "(:document_id, 'identical', 0, :identical_hash, CAST(:identical AS vector)), "
            "(:document_id, 'different', 1, :different_hash, CAST(:different AS vector))"
        ),
        {
            "document_id": document_id,
            "identical_hash": "a" * 64,
            "different_hash": "b" * 64,
            "identical": identical_vector,
            "different": different_vector,
        },
    )

    results = sync_connection.execute(
        text(
            "SELECT chunk_text, embedding <=> CAST(:query AS vector) AS distance "
            "FROM document_chunks ORDER BY distance"
        ),
        {"query": identical_vector},
    ).all()
    sync_connection.commit()

    assert results[0].chunk_text == "identical"
    assert results[0].distance == pytest.approx(0.0)
