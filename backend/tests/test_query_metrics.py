from uuid import UUID

import pytest

from app.db.models import QueryEvent
from app.services.repositories import log_query_event


class FakeSession:
    def __init__(self) -> None:
        self.added: QueryEvent | None = None
        self.flushed = False

    def add(self, event: QueryEvent) -> None:
        self.added = event
        event.id = UUID("2be66d42-8f42-4e9d-aa38-51b514607c38")

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.asyncio
async def test_log_query_event_persists_only_anonymous_metrics() -> None:
    session = FakeSession()

    event = await log_query_event(
        session,
        state="answered",
        latency_ms=42,
        retrieved_chunk_count=3,
        source_ids=[2, 1, 2],
        source_version_ids=[5, 4, 5],
        top_fused_score=0.02,
        score_gap=0.003,
    )

    assert event is session.added
    assert event.state == "answered"
    assert event.latency_ms == 42
    assert event.retrieved_chunk_count == 3
    assert event.source_ids == [1, 2]
    assert event.source_version_ids == [4, 5]
    assert event.top_fused_score == 0.02
    assert event.score_gap == 0.003
    assert not hasattr(event, "question")
    assert not hasattr(event, "answer")
    assert not hasattr(event, "chunk_ids")
    assert session.flushed is True
