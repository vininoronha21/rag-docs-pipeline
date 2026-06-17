from datetime import UTC, datetime

import pytest

from app.api import routes
from app.db.models import QueryLog
from app.schemas import QueryHistoryResponse


@pytest.mark.asyncio
async def test_query_history_returns_paginated_query_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    created_at = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    query = QueryLog(
        id=7,
        user_query="What is FastAPI?",
        retrieved_chunks_ids=[3, 4],
        llm_response="FastAPI is a Python web framework.",
        user_feedback=1,
        latency_ms=37,
        retrieved_chunk_count=2,
        created_at=created_at,
    )

    async def fake_list_queries(
        session: object, *, limit: int, offset: int
    ) -> tuple[list[QueryLog], int]:
        assert session == "session"
        assert limit == 10
        assert offset == 5
        return [query], 42

    monkeypatch.setattr(routes, "list_queries", fake_list_queries)

    response = await routes.query_history(limit=10, offset=5, session="session")

    assert response == QueryHistoryResponse(
        items=[
            {
                "id": 7,
                "question": "What is FastAPI?",
                "answer": "FastAPI is a Python web framework.",
                "retrieved_chunk_ids": [3, 4],
                "feedback": 1,
                "latency_ms": 37,
                "retrieved_chunk_count": 2,
                "created_at": created_at,
            }
        ],
        total=42,
        limit=10,
        offset=5,
    )
