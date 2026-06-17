import pytest

from app.db.models import QueryLog
from app.services.repositories import log_query


class FakeSession:
    def __init__(self) -> None:
        self.added: QueryLog | None = None
        self.flushed = False

    def add(self, query: QueryLog) -> None:
        self.added = query

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.asyncio
async def test_log_query_persists_latency_and_retrieval_metrics() -> None:
    session = FakeSession()

    query = await log_query(
        session,
        question="How do I run it?",
        retrieved_chunk_ids=[1, 2, 3],
        answer="Use the documented command.",
        latency_ms=42,
        retrieved_chunk_count=3,
    )

    assert query is session.added
    assert query.latency_ms == 42
    assert query.retrieved_chunk_count == 3
    assert session.flushed is True
