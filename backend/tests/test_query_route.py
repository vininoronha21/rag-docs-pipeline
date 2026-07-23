import logging
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.api import routes
from app.core.config import Settings
from app.schemas import QueryRequest
from app.services.embeddings import EmbeddingProviderError
from app.services.querying import Evidence, QueryExecutionMetrics, QueryExecutionResult
from app.services.rag import CitedSentence, ExtractiveAnswer


def _query_validation_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def unexpected_run_query(*args: object, **kwargs: object) -> QueryExecutionResult:
        pytest.fail("Oversized public query input should be rejected before retrieval.")

    monkeypatch.setattr(routes, "run_query", unexpected_run_query)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.dependency_overrides[routes.get_session] = lambda: object()
    app.dependency_overrides[routes.get_settings] = lambda: object()
    app.dependency_overrides[routes.get_embedding_provider] = lambda: object()
    return TestClient(app, raise_server_exceptions=False)


def test_get_embedding_provider_returns_server_error_for_invalid_configuration() -> None:
    settings = Settings(embedding_provider="openai", openai_api_key=None, _env_file=None)

    with pytest.raises(HTTPException) as exc_info:
        routes.get_embedding_provider(settings=settings)

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Embedding provider is not configured correctly" in exc_info.value.detail
    assert "OPENAI_API_KEY is required" in exc_info.value.detail


@pytest.mark.asyncio
async def test_query_route_maps_structured_answer_and_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_id = uuid4()

    async def fake_run_query(*args: object, **kwargs: object) -> QueryExecutionResult:
        return QueryExecutionResult(
            event_id=event_id,
            state="answered",
            answer=ExtractiveAnswer(
                sentences=[CitedSentence(text="FastAPI runs with Uvicorn.", chunk_id=3)]
            ),
            evidence=[
                Evidence(
                    citation_id="citation-1",
                    supported_text="FastAPI runs with Uvicorn.",
                    excerpt="FastAPI runs with Uvicorn from the command line.",
                    title="Project docs",
                    repository_path="docs/index.md",
                    section="Run",
                    commit_sha="a" * 40,
                    source_url=f"https://github.com/example/project/blob/{'a' * 40}/docs/index.md",
                    vector_score=0.8,
                    text_score=0.4,
                    fused_score=0.02,
                    chunk_id=3,
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

    response = await routes.query_docs(
        QueryRequest(question="How do I run FastAPI?", top_k=5, source="github"),
        session=object(),
        settings=object(),
        embeddings=object(),
    )

    assert response.event_id == event_id
    assert response.state == "answered"
    assert response.answer is not None
    assert response.answer.sentences[0].text == "FastAPI runs with Uvicorn."
    assert response.answer.sentences[0].citation_id == "citation-1"
    assert response.evidence[0].citation_id == "citation-1"
    assert response.evidence[0].repository_path == "docs/index.md"
    assert response.metrics.retrieved_chunk_count == 1
    payload = response.model_dump(mode="json")
    assert "chunk_id" not in payload["evidence"][0]
    assert "retrieved_chunk_ids" not in payload
    assert "query_id" not in payload


def test_query_history_route_is_absent() -> None:
    paths = {(route.path, method) for route in routes.router.routes for method in route.methods}

    assert ("/queries", "GET") not in paths
    assert ("/query-events/{event_id}/feedback", "PATCH") in paths


def test_query_route_rejects_oversized_question(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _query_validation_client(monkeypatch).post(
        "/api/query",
        json={"question": "x" * 1001, "top_k": 5},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"][0]["loc"][-1] == "question"


def test_query_route_rejects_oversized_source(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _query_validation_client(monkeypatch).post(
        "/api/query",
        json={"question": "OK?", "top_k": 5, "source": "x" * 129},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"][0]["loc"][-1] == "source"


def test_query_route_returns_insufficient_evidence_as_http_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_id = uuid4()

    async def fake_run_query(*args: object, **kwargs: object) -> QueryExecutionResult:
        return QueryExecutionResult(
            event_id=event_id,
            state="insufficient_evidence",
            answer=None,
            evidence=[
                Evidence(
                    citation_id=None,
                    supported_text=None,
                    excerpt="Closest available documentation.",
                    title="Project docs",
                    repository_path="docs/index.md",
                    section="Overview",
                    commit_sha="a" * 40,
                    source_url=f"https://github.com/example/project/blob/{'a' * 40}/docs/index.md",
                    vector_score=0.9,
                    text_score=None,
                    fused_score=0.005,
                    chunk_id=9,
                )
            ],
            metrics=QueryExecutionMetrics(
                latency_ms=8,
                retrieved_chunk_count=1,
                top_fused_score=0.005,
                score_gap=None,
            ),
        )

    monkeypatch.setattr(routes, "run_query", fake_run_query)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.dependency_overrides[routes.get_session] = lambda: object()
    app.dependency_overrides[routes.get_settings] = lambda: object()
    app.dependency_overrides[routes.get_embedding_provider] = lambda: object()

    response = TestClient(app).post(
        "/api/query",
        json={"question": "Unknown topic", "top_k": 5},
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["state"] == "insufficient_evidence"
    assert payload["answer"] is None
    assert payload["evidence"][0]["citation_id"] is None
    assert payload["evidence"][0]["excerpt"] == "Closest available documentation."


def test_query_route_sanitizes_database_errors(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question_secret = "QUESTION-DB-SECRET-7a8b9c"

    class FakeSession:
        rolled_back = False

        async def rollback(self) -> None:
            self.rolled_back = True

    fake_session = FakeSession()

    async def fake_run_query(*args: object, **kwargs: object) -> None:
        raise SQLAlchemyError(f"statement params included {question_secret}")

    monkeypatch.setattr(routes, "run_query", fake_run_query)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.dependency_overrides[routes.get_session] = lambda: fake_session
    app.dependency_overrides[routes.get_settings] = lambda: object()
    app.dependency_overrides[routes.get_embedding_provider] = lambda: object()

    with caplog.at_level(logging.WARNING, logger="app.api.routes"):
        response = TestClient(app, raise_server_exceptions=False).post(
            "/api/query",
            json={"question": f"How do I run FastAPI? {question_secret}", "top_k": 5},
        )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {
        "detail": "Query service is temporarily unavailable. Try again later."
    }
    assert fake_session.rolled_back is True
    serialized_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "public_query_database_error" in serialized_logs
    assert "SQLAlchemyError" in serialized_logs
    assert question_secret not in serialized_logs
    assert question_secret not in response.text


def test_query_route_sanitizes_database_errors_when_rollback_fails(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question_secret = "QUESTION-ROLLBACK-SECRET-2b3c4d"
    rollback_secret = "ROLLBACK-SECRET-5e6f7a"

    class FakeSession:
        async def rollback(self) -> None:
            raise SQLAlchemyError(f"rollback params included {rollback_secret}")

    async def fake_run_query(*args: object, **kwargs: object) -> None:
        raise SQLAlchemyError(f"statement params included {question_secret}")

    monkeypatch.setattr(routes, "run_query", fake_run_query)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.dependency_overrides[routes.get_session] = lambda: FakeSession()
    app.dependency_overrides[routes.get_settings] = lambda: object()
    app.dependency_overrides[routes.get_embedding_provider] = lambda: object()

    with caplog.at_level(logging.WARNING, logger="app.api.routes"):
        response = TestClient(app, raise_server_exceptions=False).post(
            "/api/query",
            json={"question": f"How do I run FastAPI? {question_secret}", "top_k": 5},
        )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    serialized_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "public_query_database_error" in serialized_logs
    assert "rollback_error" in serialized_logs
    assert "SQLAlchemyError" in serialized_logs
    assert question_secret not in serialized_logs
    assert rollback_secret not in serialized_logs
    assert question_secret not in response.text
    assert rollback_secret not in response.text


@pytest.mark.asyncio
async def test_query_route_returns_bad_gateway_for_embedding_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_query(*args: object, **kwargs: object) -> None:
        raise EmbeddingProviderError("Could not reach embedding provider. Try again later.")

    monkeypatch.setattr(routes, "run_query", fake_run_query)

    with pytest.raises(HTTPException) as exc_info:
        await routes.query_docs(
            QueryRequest(question="How do I run FastAPI?", top_k=5),
            session=object(),
            settings=object(),
            embeddings=object(),
        )

    assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY


@pytest.mark.asyncio
async def test_feedback_route_uses_uuid_event_id(monkeypatch: pytest.MonkeyPatch) -> None:
    event_id = uuid4()
    event = SimpleNamespace(id=event_id, feedback=1)

    async def fake_update(*args: object, **kwargs: object) -> object:
        assert kwargs == {"event_id": event_id, "feedback": 1}
        return event

    class AsyncSession:
        async def commit(self) -> None:
            pass

    monkeypatch.setattr(routes, "update_query_event_feedback", fake_update)

    response = await routes.record_query_feedback(
        event_id,
        routes.QueryFeedbackRequest(feedback=1),
        session=AsyncSession(),
    )

    assert response.event_id == event_id
    assert response.feedback == 1


@pytest.mark.asyncio
async def test_query_route_returns_bad_request_for_query_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_query(*args: object, **kwargs: object) -> None:
        raise ValueError("top_k must be between 1 and 12.")

    monkeypatch.setattr(routes, "run_query", fake_run_query)

    with pytest.raises(HTTPException) as exc_info:
        await routes.query_docs(
            QueryRequest(question="How do I run FastAPI?", top_k=5),
            session=object(),
            settings=object(),
            embeddings=object(),
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "top_k must be between 1 and 12."
