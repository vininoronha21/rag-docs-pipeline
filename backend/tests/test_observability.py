import json
import logging
from uuid import UUID, uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.api import routes
from app.main import create_app
from app.services.querying import Evidence, QueryExecutionMetrics, QueryExecutionResult
from app.services.rag import CitedSentence, ExtractiveAnswer


def test_query_completion_log_is_structured_and_redacted(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_secret = "REQ-SECRET-4c1f2b"
    auth_secret = "AUTH-SECRET-8a9c0d"
    query_secret = "QUERY-SECRET-5e6f7a"
    answer_secret = "ANSWER-SECRET-1b2c3d"
    excerpt_secret = "EXCERPT-SECRET-9e8d7c"
    user_agent_secret = "USER-AGENT-SECRET-3f4a5b"
    unsafe_request_id = f"caller-controlled-{request_secret}"
    event_id = uuid4()

    async def fake_run_query(*args: object, **kwargs: object) -> QueryExecutionResult:
        return QueryExecutionResult(
            event_id=event_id,
            state="answered",
            answer=ExtractiveAnswer(
                sentences=[
                    CitedSentence(text=f"Do not log {answer_secret}.", chunk_id=7)
                ]
            ),
            evidence=[
                Evidence(
                    citation_id="citation-1",
                    supported_text=f"Supported text {answer_secret}.",
                    excerpt=f"Excerpt must stay private {excerpt_secret}.",
                    title="Project docs",
                    repository_path="docs/privacy.md",
                    section="Logging",
                    commit_sha="a" * 40,
                    source_url=(
                        f"https://github.com/example/project/blob/{'a' * 40}/docs/privacy.md"
                    ),
                    vector_score=0.8,
                    text_score=0.4,
                    fused_score=0.02,
                    chunk_id=7,
                )
            ],
            metrics=QueryExecutionMetrics(
                latency_ms=12,
                retrieved_chunk_count=1,
                top_fused_score=0.02,
                score_gap=None,
            ),
        )

    monkeypatch.setattr(routes, "run_query", fake_run_query)
    app = create_app()
    app.dependency_overrides[routes.get_session] = lambda: object()
    app.dependency_overrides[routes.get_settings] = lambda: object()
    app.dependency_overrides[routes.get_embedding_provider] = lambda: object()

    with caplog.at_level(logging.INFO, logger="app.core.observability"):
        response = TestClient(app).post(
            f"/api/query?debug={query_secret}",
            headers={
                "Authorization": f"Bearer {auth_secret}",
                "User-Agent": f"privacy-check/{user_agent_secret}",
                "X-Forwarded-For": "203.0.113.88",
                "X-Request-ID": unsafe_request_id,
            },
            json={"question": f"How do I keep logs private? {request_secret}", "top_k": 5},
        )

    assert response.status_code == status.HTTP_200_OK
    records = [
        record
        for record in caplog.records
        if record.name == "app.core.observability"
    ]
    assert len(records) == 1

    log_event = json.loads(records[0].getMessage())
    assert log_event["operation"] == "query_docs"
    assert "route" not in log_event
    assert log_event["status"] == status.HTTP_200_OK
    assert isinstance(log_event["duration_ms"], int | float)
    assert log_event["duration_ms"] >= 0
    assert UUID(log_event["request_id"])
    assert log_event["request_id"] != unsafe_request_id
    assert response.headers["X-Request-ID"] == log_event["request_id"]
    assert log_event["event_id"] == str(event_id)
    assert log_event["evidence_state"] == "answered"

    serialized_log = json.dumps(log_event)
    for forbidden in (
        request_secret,
        auth_secret,
        query_secret,
        answer_secret,
        excerpt_secret,
        unsafe_request_id,
        user_agent_secret,
        "question",
        "Authorization",
        "Bearer",
        "203.0.113.88",
        "127.0.0.1",
        "/api/query",
    ):
        assert forbidden not in serialized_log
