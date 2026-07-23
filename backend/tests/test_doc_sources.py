from datetime import UTC, datetime

import pytest
from fastapi import HTTPException, status

from app.api import routes
from app.db.models import DocSource, SourceVersion
from app.schemas import DocSourceItem, DocSourceListResponse, DocSourceUpdateRequest
from app.services.repositories import get_or_create_doc_source, update_doc_source_enabled


class FakeUpsertSession:
    def __init__(self, source: DocSource | None = None) -> None:
        self.source = source
        self.inserted: DocSource | None = None
        self.executed = False

    async def execute(self, statement: object) -> None:
        assert "ON CONFLICT" in str(statement)
        self.executed = True
        if self.source is None:
            self.source = DocSource(
                source_type="github",
                source_config={"repo": "example/project", "branch": "main", "path": "docs"},
                repository="example/project",
                branch="main",
                path="docs",
                language="pt-BR",
                enabled=True,
            )
            self.inserted = self.source

    async def scalar(self, statement: object) -> DocSource | None:
        assert statement is not None
        return self.source


class FakeUpdateSession:
    def __init__(self, source: DocSource | None = None) -> None:
        self.source = source
        self.flushed = False

    async def get(self, model: type[DocSource], source_id: int) -> DocSource | None:
        assert model is DocSource
        if self.source is None or self.source.id != source_id:
            return None
        return self.source

    async def scalar(self, statement: object) -> DocSource | None:
        assert statement is not None
        if self.source is None or self.source.id != 3:
            return None
        return self.source

    async def flush(self) -> None:
        self.flushed = True


class FakeRouteSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_get_or_create_doc_source_creates_missing_source() -> None:
    session = FakeUpsertSession()

    source = await get_or_create_doc_source(
        session,
        repository="example/project",
        branch="main",
        path="docs",
    )

    assert source is session.inserted
    assert source.source_type == "github"
    assert source.source_config["repo"] == "example/project"
    assert source.repository == "example/project"
    assert source.branch == "main"
    assert source.path == "docs"
    assert source.language == "pt-BR"
    assert source.last_sync is None
    assert source.enabled is True
    assert session.executed is True


@pytest.mark.asyncio
async def test_get_or_create_doc_source_returns_existing_without_mutating_sync_state() -> None:
    old_sync = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
    existing = DocSource(
        id=3,
        source_type="github",
        source_config={"repo": "example/project", "branch": "main", "path": ""},
        repository="example/project",
        branch="main",
        path="",
        language="pt-BR",
        last_sync=old_sync,
        enabled=False,
    )
    session = FakeUpsertSession(existing)

    source = await get_or_create_doc_source(
        session,
        repository="example/project",
        branch="main",
        path="",
    )

    assert source is existing
    assert source.last_sync == old_sync
    assert source.enabled is False
    assert session.inserted is None
    assert session.executed is True


@pytest.mark.asyncio
async def test_doc_sources_route_returns_source_items(monkeypatch: pytest.MonkeyPatch) -> None:
    synced_at = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
    source = DocSource(
        id=3,
        source_type="github",
        source_config={"repo": "example/project", "branch": "main", "path": ""},
        last_sync=synced_at,
        enabled=True,
    )
    source.active_version = SourceVersion(
        id=8,
        source_id=3,
        commit_sha="a" * 40,
        embedding_provider="local",
        embedding_model="hash",
        embedding_dimensions=1536,
        document_count=2,
        chunk_count=14,
    )

    async def fake_list_doc_sources(session: object) -> list[DocSource]:
        assert session == "session"
        return [source]

    monkeypatch.setattr(routes, "list_doc_sources", fake_list_doc_sources)

    response = await routes.doc_sources(session="session")

    assert response == DocSourceListResponse(
        items=[
            {
                "id": 3,
                "source_type": "github",
                "source_config": {"repo": "example/project", "branch": "main", "path": ""},
                "last_sync": synced_at,
                "enabled": True,
                "active_version_id": 8,
                "active_commit_sha": "a" * 40,
                "active_document_count": 2,
                "active_chunk_count": 14,
            }
        ]
    )


@pytest.mark.asyncio
async def test_update_doc_source_enabled_updates_existing_source() -> None:
    source = DocSource(
        id=3,
        source_type="github",
        source_config={"repo": "example/project", "branch": "main", "path": ""},
        enabled=True,
    )
    session = FakeUpdateSession(source)

    updated = await update_doc_source_enabled(session, source_id=3, enabled=False)

    assert updated is source
    assert source.enabled is False
    assert session.flushed is True


@pytest.mark.asyncio
async def test_update_doc_source_enabled_returns_none_for_missing_source() -> None:
    session = FakeUpdateSession()

    updated = await update_doc_source_enabled(session, source_id=404, enabled=False)

    assert updated is None
    assert session.flushed is False


@pytest.mark.asyncio
async def test_update_doc_source_route_returns_updated_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synced_at = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
    source = DocSource(
        id=3,
        source_type="github",
        source_config={"repo": "example/project", "branch": "main", "path": ""},
        last_sync=synced_at,
        enabled=False,
    )
    source.active_version = SourceVersion(
        id=9,
        source_id=3,
        commit_sha="b" * 40,
        embedding_provider="local",
        embedding_model="hash",
        embedding_dimensions=1536,
        document_count=3,
        chunk_count=21,
    )

    async def fake_update_doc_source_enabled(
        session: object, *, source_id: int, enabled: bool
    ) -> DocSource:
        assert source_id == 3
        assert enabled is False
        return source

    session = FakeRouteSession()
    monkeypatch.setattr(routes, "update_doc_source_enabled", fake_update_doc_source_enabled)

    response = await routes.update_doc_source(
        3,
        DocSourceUpdateRequest(enabled=False),
        session=session,
    )

    assert response == DocSourceItem(
        id=3,
        source_type="github",
        source_config={"repo": "example/project", "branch": "main", "path": ""},
        last_sync=synced_at,
        enabled=False,
        active_version_id=9,
        active_commit_sha="b" * 40,
        active_document_count=3,
        active_chunk_count=21,
    )
    assert session.committed is True


@pytest.mark.asyncio
async def test_update_doc_source_route_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_update_doc_source_enabled(
        session: object, *, source_id: int, enabled: bool
    ) -> None:
        assert source_id == 404
        assert enabled is False
        return None

    monkeypatch.setattr(routes, "update_doc_source_enabled", fake_update_doc_source_enabled)

    with pytest.raises(HTTPException) as exc_info:
        await routes.update_doc_source(
            404,
            DocSourceUpdateRequest(enabled=False),
            session=FakeRouteSession(),
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Document source not found."
