import pytest
from pydantic import ValidationError

from app.db.models import QueryLog
from app.schemas import QueryFeedbackRequest
from app.services.repositories import update_query_feedback


class FakeSession:
    def __init__(self, query: QueryLog | None) -> None:
        self.query = query
        self.flushed = False

    async def get(self, model: type[QueryLog], query_id: int) -> QueryLog | None:
        assert model is QueryLog
        if self.query is None or self.query.id != query_id:
            return None
        return self.query

    async def flush(self) -> None:
        self.flushed = True


def test_query_feedback_accepts_negative_neutral_and_positive_scores() -> None:
    for value in (-1, 0, 1):
        assert QueryFeedbackRequest(feedback=value).feedback == value


def test_query_feedback_rejects_scores_outside_supported_range() -> None:
    with pytest.raises(ValidationError):
        QueryFeedbackRequest(feedback=2)


@pytest.mark.asyncio
async def test_update_query_feedback_updates_existing_query() -> None:
    query = QueryLog(
        id=12,
        user_query="How do I run it?",
        retrieved_chunks_ids=[1, 2],
        llm_response="Use the documented command.",
    )
    session = FakeSession(query)

    updated = await update_query_feedback(session, query_id=12, feedback=1)

    assert updated is query
    assert query.user_feedback == 1
    assert session.flushed is True


@pytest.mark.asyncio
async def test_update_query_feedback_returns_none_for_missing_query() -> None:
    session = FakeSession(None)

    updated = await update_query_feedback(session, query_id=404, feedback=-1)

    assert updated is None
    assert session.flushed is False
