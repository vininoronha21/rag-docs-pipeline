import pytest
from sqlalchemy import Connection, text

from app.services.repositories import retrieve_chunks


class AsyncConnectionAdapter:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    async def execute(self, statement: object, params: dict[str, object]) -> object:
        return self.connection.execute(statement, params)


def _vector(first: float = 0, second: float = 0) -> str:
    return "[" + ",".join([str(first), str(second)] + ["0"] * 1534) + "]"


def _insert_source(connection: Connection, *, suffix: str, enabled: bool = True) -> tuple[int, int]:
    source_id = connection.execute(
        text(
            "INSERT INTO doc_sources "
            "(source_type, source_config, enabled, repository, branch, path, language) "
            "VALUES ('github', '{}', :enabled, :repository, 'main', 'docs', 'pt-BR') "
            "RETURNING id"
        ),
        {"enabled": enabled, "repository": f"hybrid/{suffix}"},
    ).scalar_one()
    version_id = connection.execute(
        text(
            "INSERT INTO source_versions "
            "(source_id, commit_sha, embedding_provider, embedding_model, "
            "embedding_dimensions, document_count, chunk_count) "
            "VALUES (:source_id, :sha, 'local', 'hash', 1536, 1, 1) RETURNING id"
        ),
        {"source_id": source_id, "sha": suffix.rjust(40, "0")[-40:]},
    ).scalar_one()
    return source_id, version_id


def _insert_chunk(
    connection: Connection,
    *,
    version_id: int,
    suffix: str,
    chunk_text: str,
    embedding: str,
) -> int:
    document_id = connection.execute(
        text(
            "INSERT INTO documents "
            "(source_version_id, repository_path, source, source_url, title, content) "
            "VALUES (:version_id, :path, 'github', :url, :title, :content) RETURNING id"
        ),
        {
            "version_id": version_id,
            "path": f"docs/{suffix}.md",
            "url": f"https://example.com/{suffix}",
            "title": suffix,
            "content": chunk_text,
        },
    ).scalar_one()
    return connection.execute(
        text(
            "INSERT INTO document_chunks "
            "(document_id, chunk_text, chunk_index, chunk_hash, embedding) "
            "VALUES (:document_id, :chunk_text, 0, :chunk_hash, CAST(:embedding AS vector)) "
            "RETURNING id"
        ),
        {
            "document_id": document_id,
            "chunk_text": chunk_text,
            "chunk_hash": suffix.ljust(64, "0")[:64],
            "embedding": embedding,
        },
    ).scalar_one()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_hybrid_retrieval_fuses_active_candidates_and_handles_empty_arms(
    sync_connection: Connection,
) -> None:
    transaction = sync_connection.begin_nested()
    active_source_id, active_version_id = _insert_source(sync_connection, suffix="active")
    fused_id = _insert_chunk(
        sync_connection,
        version_id=active_version_id,
        suffix="fused",
        chunk_text="termoexato instalação principal",
        embedding=_vector(0.99, 0.1),
    )
    vector_id = _insert_chunk(
        sync_connection,
        version_id=active_version_id,
        suffix="vector",
        chunk_text="conteúdo sem correspondência lexical",
        embedding=_vector(1, 0),
    )
    exact_id = _insert_chunk(
        sync_connection,
        version_id=active_version_id,
        suffix="exact",
        chunk_text="termoexato termoexato referência textual",
        embedding=_vector(),
    )
    inactive_version_id = sync_connection.execute(
        text(
            "INSERT INTO source_versions "
            "(source_id, commit_sha, embedding_provider, embedding_model, "
            "embedding_dimensions, document_count, chunk_count) "
            "VALUES (:source_id, :sha, 'local', 'hash', 1536, 1, 1) RETURNING id"
        ),
        {"source_id": active_source_id, "sha": "i" * 40},
    ).scalar_one()
    inactive_id = _insert_chunk(
        sync_connection,
        version_id=inactive_version_id,
        suffix="inactive",
        chunk_text="termoexato termoexato termoexato",
        embedding=_vector(1, 0),
    )
    disabled_source_id, disabled_version_id = _insert_source(
        sync_connection, suffix="disabled", enabled=False
    )
    disabled_id = _insert_chunk(
        sync_connection,
        version_id=disabled_version_id,
        suffix="disabled",
        chunk_text="termoexato termoexato termoexato",
        embedding=_vector(1, 0),
    )
    sync_connection.execute(
        text("UPDATE doc_sources SET active_version_id = :version_id WHERE id = :source_id"),
        {"source_id": active_source_id, "version_id": active_version_id},
    )
    sync_connection.execute(
        text("UPDATE doc_sources SET active_version_id = :version_id WHERE id = :source_id"),
        {"source_id": disabled_source_id, "version_id": disabled_version_id},
    )
    session = AsyncConnectionAdapter(sync_connection)

    fused = await retrieve_chunks(
        session,
        question="termoexato",
        embedding=[1.0] + [0.0] * 1535,
        top_k=3,
        candidate_k=10,
        rrf_k=60,
        vector_weight=0.5,
        text_weight=0.5,
        source="github",
        source_id=active_source_id,
    )

    assert fused[0].id == fused_id
    assert fused[0].vector_rank is not None
    assert fused[0].text_rank is not None
    assert {chunk.id for chunk in fused} == {fused_id, vector_id, exact_id}
    assert inactive_id not in {chunk.id for chunk in fused}
    assert disabled_id not in {chunk.id for chunk in fused}
    assert next(chunk for chunk in fused if chunk.id == exact_id).vector_score is None

    unscoped = await retrieve_chunks(
        session,
        question="termoexato",
        embedding=[1.0] + [0.0] * 1535,
        top_k=4,
        candidate_k=10,
        rrf_k=60,
        vector_weight=0.5,
        text_weight=0.5,
        source="github",
    )

    assert disabled_id not in {chunk.id for chunk in unscoped}
    assert inactive_id not in {chunk.id for chunk in unscoped}

    sync_connection.execute(
        text("UPDATE doc_sources SET enabled = TRUE WHERE id = :source_id"),
        {"source_id": disabled_source_id},
    )
    enabled_competition = await retrieve_chunks(
        session,
        question="termoexato",
        embedding=[1.0] + [0.0] * 1535,
        top_k=4,
        candidate_k=10,
        rrf_k=60,
        vector_weight=0.5,
        text_weight=0.5,
        source="github",
    )

    assert disabled_id in {chunk.id for chunk in enabled_competition}
    assert inactive_id not in {chunk.id for chunk in enabled_competition}

    exact_only = await retrieve_chunks(
        session,
        question="termoexato",
        embedding=[0.0] * 1536,
        top_k=2,
        candidate_k=10,
        rrf_k=60,
        vector_weight=0.5,
        text_weight=0.5,
        source_id=active_source_id,
    )
    vector_only = await retrieve_chunks(
        session,
        question="de e",
        embedding=[1.0] + [0.0] * 1535,
        top_k=2,
        candidate_k=10,
        rrf_k=60,
        vector_weight=0.5,
        text_weight=0.5,
        source_id=active_source_id,
    )

    assert exact_id in {chunk.id for chunk in exact_only}
    assert all(chunk.vector_score is None for chunk in exact_only)
    assert vector_only[0].id == vector_id
    assert all(chunk.text_score is None for chunk in vector_only)
    transaction.rollback()
    sync_connection.rollback()


@pytest.mark.integration
def test_hybrid_candidate_query_is_executable_with_indexes_available(
    sync_connection: Connection,
) -> None:
    vector_plan = "\n".join(
        row[0]
        for row in sync_connection.execute(
            text(
                "EXPLAIN WITH vector_candidates AS ("
                "SELECT dc.id, 1 - (dc.embedding <=> CAST(:embedding AS vector)) "
                "AS vector_score, row_number() OVER (ORDER BY dc.embedding <=> "
                "CAST(:embedding AS vector), dc.id) AS vector_rank "
                "FROM document_chunks dc "
                "JOIN documents d ON d.id = dc.document_id "
                "JOIN source_versions sv ON sv.id = d.source_version_id "
                "JOIN doc_sources ds ON ds.id = sv.source_id "
                "WHERE d.source = :source AND ds.id = :source_id "
                "AND ds.active_version_id = sv.id AND ds.enabled IS TRUE "
                "AND vector_norm(CAST(:embedding AS vector)) > 0 "
                "AND vector_norm(dc.embedding) > 0 "
                "ORDER BY dc.embedding <=> CAST(:embedding AS vector), dc.id "
                "LIMIT :candidate_k) SELECT * FROM vector_candidates"
            ),
            {
                "embedding": _vector(1, 0),
                "source": "github",
                "source_id": 1,
                "candidate_k": 10,
            },
        )
    )
    index_names = set(
        sync_connection.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'document_chunks'"
            )
        ).scalars()
    )

    assert "Limit" in vector_plan
    assert "document_chunks" in vector_plan
    assert "ix_document_chunks_embedding_hnsw" in index_names
    assert "ix_document_chunks_search_vector_gin" in index_names
    sync_connection.rollback()
