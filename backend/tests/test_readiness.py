from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import status

from app.db.session import get_session
from app.main import create_app


class FailingSession:
    async def execute(self, statement: object) -> object:
        assert statement is not None
        raise RuntimeError(
            "postgresql://rag:secret@db.internal:5432/rag_docs SELECT 1 exploded"
        )


@pytest.fixture
async def app_client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def test_health_is_liveness_and_does_not_access_database() -> None:
    async def fail_if_database_is_requested() -> AsyncIterator[object]:
        raise AssertionError("health must not request a database session")
        yield

    app = create_app()
    app.dependency_overrides[get_session] = fail_if_database_is_requested
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/health")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "ok"


async def test_ready_returns_ready_when_database_and_pgvector_are_available(
    app_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check_readiness(session: object, request_id: str | None) -> object:
        assert session is not None
        assert request_id is not None
        return {"status": "ready", "database": "ok", "pgvector": "ok"}

    from app.api import routes

    monkeypatch.setattr(routes, "check_readiness", fake_check_readiness, raising=False)

    response = await app_client.get("/api/ready", headers={"X-Request-ID": "ready-test"})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ready", "database": "ok", "pgvector": "ok"}


async def test_ready_returns_sanitized_not_ready_response_for_database_failure() -> None:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: FailingSession()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/ready", headers={"X-Request-ID": "safe-request"})

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {"status": "not_ready", "database": "error", "pgvector": "unknown"}

    body = response.text.lower()
    for forbidden in (
        "postgresql://",
        "select 1",
        "exploded",
        "db.internal",
        "secret",
        "rag_docs",
    ):
        assert forbidden not in body
