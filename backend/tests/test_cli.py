from types import SimpleNamespace

import pytest

from app import cli as cli_module
from app.services.querying import QueryExecutionResult


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_cli_query_filters_logs_and_returns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    settings = SimpleNamespace(retrieval_min_score=0.1)
    embeddings = object()

    async def fake_run_query(*args: object, **kwargs: object) -> QueryExecutionResult:
        assert args == (session,)
        assert kwargs == {
            "question": "How do I run FastAPI?",
            "top_k": 5,
            "source": "github",
            "settings": settings,
            "embeddings": embeddings,
        }
        return QueryExecutionResult(
            query_id=7,
            answer="FastAPI runs with Uvicorn from the command line.",
            chunks=[],
            retrieved_chunk_ids=[3],
            latency_ms=15,
            retrieved_chunk_count=1,
        )

    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    monkeypatch.setattr(cli_module, "build_embedding_provider", lambda _settings: embeddings)
    monkeypatch.setattr(cli_module, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(cli_module, "run_query", fake_run_query)

    answer, query_id, retrieved_chunk_count, _latency_ms = await cli_module._run_query(
        "How do I run FastAPI?",
        top_k=5,
        source="github",
    )

    assert "FastAPI runs with Uvicorn" in answer
    assert query_id == 7
    assert retrieved_chunk_count == 1
