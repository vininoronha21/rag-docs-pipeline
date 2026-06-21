from types import SimpleNamespace

import pytest

from app.api import routes
from app.schemas import QueryRequest
from app.services.querying import QueryExecutionResult
from app.services.repositories import RetrievedChunk


def make_chunk(chunk_id: int, score: float, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        document_id=10,
        text=text,
        chunk_index=0,
        metadata={"source_path": "docs/index.md", "section": "Run"},
        title="Project docs",
        source_url="https://github.com/example/project/blob/main/docs/index.md",
        source="github",
        score=score,
    )


@pytest.mark.asyncio
async def test_query_route_retrieves_filters_answers_and_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    embeddings = object()
    settings = SimpleNamespace(retrieval_min_score=0.1)

    async def fake_run_query(*args: object, **kwargs: object) -> QueryExecutionResult:
        assert args == (session,)
        assert kwargs == {
            "question": "How do I run FastAPI?",
            "top_k": 5,
            "source": "github",
            "settings": settings,
            "embeddings": embeddings,
        }
        chunk = make_chunk(3, 0.8, "FastAPI runs with Uvicorn from the command line.")
        return QueryExecutionResult(
            query_id=42,
            answer="FastAPI runs with Uvicorn from the command line.",
            chunks=[chunk],
            retrieved_chunk_ids=[3],
            latency_ms=12,
            retrieved_chunk_count=1,
        )

    monkeypatch.setattr(routes, "run_query", fake_run_query)

    response = await routes.query_docs(
        QueryRequest(question="How do I run FastAPI?", top_k=5, source="github"),
        session=session,
        settings=settings,
        embeddings=embeddings,
    )

    assert response.query_id == 42
    assert response.retrieved_chunk_ids == [3]
    assert response.latency_ms == 12
    assert response.retrieved_chunk_count == 1
    assert response.citations[0].chunk_id == 3
    assert "FastAPI runs with Uvicorn" in response.answer
