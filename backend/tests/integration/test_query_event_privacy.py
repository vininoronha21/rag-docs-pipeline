from uuid import UUID

import pytest
from sqlalchemy import Connection, inspect, text

from app.db.models import DocumentChunk, QueryEvent


@pytest.mark.integration
def test_query_events_store_only_anonymous_metrics(sync_connection: Connection) -> None:
    columns = {
        column["name"]: column for column in inspect(sync_connection).get_columns("query_events")
    }

    assert set(columns) == {
        "id",
        "state",
        "latency_ms",
        "retrieved_chunk_count",
        "source_ids",
        "source_version_ids",
        "top_fused_score",
        "score_gap",
        "feedback",
        "created_at",
    }
    assert {
        "user_query",
        "question",
        "llm_response",
        "answer",
        "excerpt",
        "retrieved_chunks_ids",
        "chunk_ids",
        "ip_address",
        "user_agent",
    }.isdisjoint(columns)
    assert sync_connection.execute(text("SELECT to_regclass('queries')")).scalar_one() is None


@pytest.mark.integration
def test_query_event_defaults_and_checks_are_enforced(sync_connection: Connection) -> None:
    event = sync_connection.execute(
        text(
            "INSERT INTO query_events "
            "(state, latency_ms, retrieved_chunk_count, source_ids, source_version_ids, "
            "top_fused_score, score_gap, feedback) "
            "VALUES ('answered', 25, 3, ARRAY[1, 2], ARRAY[4], 0.75, 0.2, 1) "
            "RETURNING id, created_at"
        )
    ).one()
    constraints = " ".join(
        sync_connection.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'query_events'::regclass AND contype = 'c'"
            )
        ).scalars()
    )
    sync_connection.rollback()

    assert isinstance(event.id, UUID)
    assert event.created_at is not None
    assert "answered" in constraints and "insufficient_evidence" in constraints
    assert "latency_ms >= 0" in constraints
    assert "retrieved_chunk_count >= 0" in constraints
    assert "feedback" in constraints and "-1" in constraints and "1" in constraints


def test_orm_matches_anonymous_event_and_generated_search_schema() -> None:
    assert set(QueryEvent.__table__.columns.keys()) == {
        "id",
        "state",
        "latency_ms",
        "retrieved_chunk_count",
        "source_ids",
        "source_version_ids",
        "top_fused_score",
        "score_gap",
        "feedback",
        "created_at",
    }
    assert str(DocumentChunk.__table__.c.search_vector.type) == "TSVECTOR"
    assert str(DocumentChunk.__table__.c.search_vector.computed.sqltext) == (
        "to_tsvector('portuguese', coalesce(chunk_text, ''))"
    )
