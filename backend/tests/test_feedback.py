from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.db.models import QueryEvent
from app.schemas import QueryFeedbackRequest
from app.services.repositories import update_query_event_feedback


class FakeSession:
    def __init__(self, event: QueryEvent | None) -> None:
        self.event = event
        self.flushed = False

    async def get(self, model: type[QueryEvent], event_id: UUID) -> QueryEvent | None:
        assert model is QueryEvent
        if self.event is None or self.event.id != event_id:
            return None
        return self.event

    async def flush(self) -> None:
        self.flushed = True


def test_query_feedback_accepts_only_negative_and_positive_scores() -> None:
    assert QueryFeedbackRequest(feedback=-1).feedback == -1
    assert QueryFeedbackRequest(feedback=1).feedback == 1
    for value in (0, 2, -2):
        with pytest.raises(ValidationError):
            QueryFeedbackRequest(feedback=value)


@pytest.mark.asyncio
async def test_update_query_event_feedback_updates_existing_event() -> None:
    event_id = uuid4()
    event = QueryEvent(
        id=event_id,
        state="answered",
        latency_ms=12,
        retrieved_chunk_count=1,
        source_ids=[1],
        source_version_ids=[2],
    )
    session = FakeSession(event)

    updated = await update_query_event_feedback(session, event_id=event_id, feedback=1)

    assert updated is event
    assert event.feedback == 1
    assert session.flushed is True


@pytest.mark.asyncio
async def test_update_query_event_feedback_returns_none_for_missing_event() -> None:
    session = FakeSession(None)

    updated = await update_query_event_feedback(session, event_id=uuid4(), feedback=-1)

    assert updated is None
    assert session.flushed is False
