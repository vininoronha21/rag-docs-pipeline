from datetime import UTC, datetime

import pytest

from app.db.models import DocSource, SourceVersion
from app.services import repositories


class FakePromotionSession:
    def __init__(self) -> None:
        self.executed: list[object] = []
        self.flush_count = 0

    async def execute(self, statement: object) -> None:
        self.executed.append(statement)

    async def flush(self) -> None:
        self.flush_count += 1


class FakeCreationSession:
    def __init__(self, source: DocSource) -> None:
        self.source = source
        self.actions: list[tuple[str, object]] = []

    async def execute(self, statement: object) -> None:
        self.actions.append(("execute", statement))

    async def scalar(self, statement: object) -> DocSource:
        self.actions.append(("scalar", statement))
        return self.source


def make_source(source_id: int, *, active_version_id: int | None = None) -> DocSource:
    return DocSource(
        id=source_id,
        source_type="github",
        source_config={"repo": "example/project", "branch": "main", "path": "docs"},
        repository="example/project",
        branch="main",
        path="docs",
        language="pt-BR",
        active_version_id=active_version_id,
        enabled=True,
    )


def make_version(version_id: int, source_id: int) -> SourceVersion:
    return SourceVersion(
        id=version_id,
        source_id=source_id,
        commit_sha=f"{version_id:040x}",
        synced_at=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
        embedding_provider="local",
        embedding_model="hash",
        embedding_dimensions=2,
        document_count=1,
        chunk_count=1,
    )


@pytest.mark.asyncio
async def test_get_or_create_doc_source_uses_race_safe_insert_before_select() -> None:
    source = make_source(1)
    session = FakeCreationSession(source)

    result = await repositories.get_or_create_doc_source(
        session,
        repository="example/project",
        branch="main",
        path="docs",
    )

    assert result is source
    assert [action for action, _statement in session.actions] == ["execute", "scalar"]
    insert_sql = str(session.actions[0][1])
    assert "INSERT INTO doc_sources" in insert_sql
    assert "ON CONFLICT" in insert_sql
    assert "DO NOTHING" in insert_sql


@pytest.mark.asyncio
async def test_get_doc_source_for_update_locks_source_row() -> None:
    source = make_source(1)
    session = FakeCreationSession(source)

    result = await repositories.get_doc_source_for_update(session, source_id=1)

    assert result is source
    assert "FOR UPDATE" in str(session.actions[0][1])


@pytest.mark.asyncio
async def test_promote_source_version_rejects_cross_source_before_mutation() -> None:
    session = FakePromotionSession()
    source = make_source(1, active_version_id=7)
    version = make_version(8, source_id=2)

    with pytest.raises(ValueError, match="does not belong to source"):
        await repositories.promote_source_version(session, source=source, version=version)

    assert source.active_version_id == 7
    assert source.last_sync is None
    assert session.executed == []
    assert session.flush_count == 0


@pytest.mark.asyncio
async def test_promote_source_version_updates_pointer_sync_and_prunes_inactive_versions() -> None:
    session = FakePromotionSession()
    source = make_source(1, active_version_id=7)
    version = make_version(8, source_id=1)

    await repositories.promote_source_version(session, source=source, version=version, retention=5)

    assert source.active_version_id == 8
    assert source.last_sync == version.synced_at
    assert session.flush_count == 1
    assert len(session.executed) == 1
    sql = str(session.executed[0])
    assert "source_versions.source_id" in sql
    assert "source_versions.id !=" in sql
    assert "source_versions.synced_at DESC" in sql
    assert "source_versions.id DESC" in sql
    assert "OFFSET" in sql
