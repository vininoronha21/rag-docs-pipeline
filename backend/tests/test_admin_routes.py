import json
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import status

from app.core.config import Settings, get_settings
from app.db.models import DocSource, SourceVersion
from app.db.session import get_session
from app.main import create_app

ADMIN_SECRET = secrets.token_urlsafe(24)


class FakeScalarResult:
    def __init__(self, items: list[DocSource]) -> None:
        self._items = items

    def all(self) -> list[DocSource]:
        return self._items


class FakeAdminSession:
    def __init__(self) -> None:
        self.source = DocSource(
            id=3,
            source_type="github",
            source_config={"repo": "example/project", "branch": "main", "path": "docs"},
            last_sync=datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
            enabled=True,
        )
        self.source.active_version = SourceVersion(
            id=8,
            source_id=3,
            commit_sha="a" * 40,
            embedding_provider="local",
            embedding_model="hash",
            embedding_dimensions=1536,
            document_count=2,
            chunk_count=14,
        )
        self.committed = False

    async def scalars(self, statement: object) -> FakeScalarResult:
        assert statement is not None
        return FakeScalarResult([self.source])

    async def scalar(self, statement: object) -> int:
        assert statement is not None
        return 0

    async def get(self, model: type[DocSource], source_id: int) -> DocSource | None:
        assert model is DocSource
        if source_id != self.source.id:
            return None
        return self.source

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True


@pytest.fixture
async def app_client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        admin_secret=ADMIN_SECRET,
        _env_file=None,
    )
    app.dependency_overrides[get_session] = lambda: FakeAdminSession()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.parametrize("header", [None, "Bearer wrong", "Basic secret"])
async def test_admin_sources_rejects_invalid_credentials(app_client, header):
    headers = {} if header is None else {"Authorization": header}
    response = await app_client.get("/api/admin/sources", headers=headers)
    assert response.status_code == 401


async def test_admin_sources_accepts_valid_bearer(app_client: httpx.AsyncClient) -> None:
    response = await app_client.get(
        "/api/admin/sources",
        headers={"Authorization": f"Bearer {ADMIN_SECRET}"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["items"] == [
        {
            "id": 3,
            "source_type": "github",
            "source_config": {"repo": "example/project", "branch": "main", "path": "docs"},
            "last_sync": "2026-07-21T12:00:00Z",
            "enabled": True,
            "active_version_id": 8,
            "active_commit_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "active_document_count": 2,
            "active_chunk_count": 14,
        }
    ]


async def test_admin_analytics_accepts_valid_bearer(app_client: httpx.AsyncClient) -> None:
    response = await app_client.get(
        "/api/admin/analytics/summary",
        headers={"Authorization": f"Bearer {ADMIN_SECRET}"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "document_count": 0,
        "chunk_count": 0,
        "active_document_count": 0,
        "active_chunk_count": 0,
        "source_count": 0,
        "enabled_source_count": 0,
        "query_count": 0,
        "average_latency_ms": 0.0,
        "positive_feedback_count": 0,
        "negative_feedback_count": 0,
    }


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/api/sources", None),
        ("patch", "/api/sources/3", None),
        ("post", "/api/ingest/github", {}),
        ("get", "/api/analytics/summary", None),
    ],
)
async def test_legacy_public_management_paths_return_404(
    app_client: httpx.AsyncClient,
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    request = getattr(app_client, method)
    kwargs = {"headers": {"Authorization": f"Bearer {ADMIN_SECRET}"}}
    if body is not None:
        kwargs["json"] = body

    response = await request(path, **kwargs)

    assert response.status_code == status.HTTP_404_NOT_FOUND


async def test_admin_management_routes_reject_missing_bearer(
    app_client: httpx.AsyncClient,
) -> None:
    responses = [
        await app_client.post(
            "/api/admin/ingest/github",
            json={"repo_url": "https://github.com/example/project", "path": "docs"},
        ),
        await app_client.patch("/api/admin/sources/3", json={"enabled": False}),
        await app_client.get("/api/admin/analytics/summary"),
    ]

    assert [response.status_code for response in responses] == [
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_401_UNAUTHORIZED,
    ]


def test_openapi_exposes_protected_admin_router_without_token_example() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        admin_secret=ADMIN_SECRET,
        _env_file=None,
    )

    schema = app.openapi()

    assert "/api/admin/sources" in schema["paths"]
    assert schema["paths"]["/api/admin/sources"]["get"]["security"]
    assert "/api/sources" not in schema["paths"]
    assert ADMIN_SECRET not in json.dumps(schema)
