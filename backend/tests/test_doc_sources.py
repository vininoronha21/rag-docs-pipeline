from datetime import UTC, datetime

import pytest

from app.api import routes
from app.db.models import DocSource
from app.schemas import DocSourceListResponse
from app.services.repositories import upsert_doc_source


class FakeUpsertSession:
    def __init__(self, source: DocSource | None = None) -> None:
        self.source = source
        self.added: DocSource | None = None
        self.flushed = False

    async def scalar(self, statement: object) -> DocSource | None:
        assert statement is not None
        return self.source

    def add(self, source: DocSource) -> None:
        self.added = source

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.asyncio
async def test_upsert_doc_source_creates_missing_source() -> None:
    synced_at = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
    session = FakeUpsertSession()

    source = await upsert_doc_source(
        session,
        source_type="github",
        source_config={"repo": "example/project", "branch": "main", "path": ""},
        last_sync=synced_at,
    )

    assert source is session.added
    assert source.source_type == "github"
    assert source.source_config["repo"] == "example/project"
    assert source.last_sync == synced_at
    assert source.enabled is True
    assert session.flushed is True


@pytest.mark.asyncio
async def test_upsert_doc_source_updates_existing_source() -> None:
    old_sync = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
    new_sync = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
    existing = DocSource(
        id=3,
        source_type="github",
        source_config={"repo": "example/project", "branch": "main", "path": ""},
        last_sync=old_sync,
        enabled=False,
    )
    session = FakeUpsertSession(existing)

    source = await upsert_doc_source(
        session,
        source_type="github",
        source_config=existing.source_config,
        last_sync=new_sync,
    )

    assert source is existing
    assert source.last_sync == new_sync
    assert source.enabled is True
    assert session.added is None
    assert session.flushed is True


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
            }
        ]
    )
