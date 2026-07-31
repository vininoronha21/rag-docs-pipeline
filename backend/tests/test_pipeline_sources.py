from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import pipeline

COMMIT_SHA = "a" * 40
OTHER_SHA = "c" * 40


class FakeSession:
    def __init__(self) -> None:
        self.transaction_open = False
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1
        self.transaction_open = False

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.transaction_open = False


class FakeEmbeddings:
    dimensions = 2

    def __init__(self, session: FakeSession) -> None:
        async def embed(texts: list[str]) -> list[list[float]]:
            assert session.transaction_open is False
            assert session.commits == 0
            return [[1.0, 0.0] for _text in texts]

        self.embed_texts = AsyncMock(side_effect=embed)


class FailingEmbeddings(FakeEmbeddings):
    def __init__(self, session: FakeSession) -> None:
        async def fail(texts: list[str]) -> list[list[float]]:
            assert session.transaction_open is False
            assert session.commits == 0
            raise RuntimeError("embedding failure")

        self.embed_texts = AsyncMock(side_effect=fail)


def make_settings() -> SimpleNamespace:
    return SimpleNamespace(
        embedding_provider="local",
        embedding_dimensions=2,
        openai_embedding_model="text-embedding-3-small",
    )


def install_github(
    monkeypatch: pytest.MonkeyPatch,
    session: FakeSession,
    *,
    before_fetch: Callable[[], None] | None = None,
    files: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    async def assert_outside_transaction(*args: object, **kwargs: object) -> object:
        assert session.transaction_open is False
        return SimpleNamespace(full_name="example/project", default_branch="main")

    async def resolve(*args: object, **kwargs: object) -> str:
        assert session.transaction_open is False
        return COMMIT_SHA

    async def fetch(*args: object, **kwargs: object) -> list[SimpleNamespace]:
        assert session.transaction_open is False
        assert session.commits == 0
        if before_fetch is not None:
            before_fetch()
        default_files = [
            SimpleNamespace(
                path="docs/index.md",
                html_url=f"https://github.com/example/project/blob/{COMMIT_SHA}/docs/index.md",
                sha="b" * 40,
                content="# Install\n\nRun the server.",
            )
        ]
        return default_files if files is None else files

    github = SimpleNamespace(
        get_repo=AsyncMock(side_effect=assert_outside_transaction),
        resolve_commit=AsyncMock(side_effect=resolve),
        fetch_markdown_files=AsyncMock(side_effect=fetch),
        close=AsyncMock(),
    )
    monkeypatch.setattr(pipeline, "GithubClient", lambda _settings: github)
    return github


def install_repositories(
    monkeypatch: pytest.MonkeyPatch,
    session: FakeSession,
    *,
    observed_active: SimpleNamespace | None,
    locked_source: SimpleNamespace,
    locked_active: SimpleNamespace | None,
    existing_version: SimpleNamespace | None = None,
    source_exists: bool = True,
) -> dict[str, AsyncMock]:
    source = (
        SimpleNamespace(id=9, active_version_id=getattr(observed_active, "id", None))
        if source_exists
        else None
    )

    async def get_or_create(*args: object, **kwargs: object) -> SimpleNamespace:
        session.transaction_open = True
        return locked_source

    active_values = iter(([observed_active] if source_exists else []) + [locked_active])

    async def get_active(*args: object, **kwargs: object) -> SimpleNamespace | None:
        session.transaction_open = True
        return next(active_values)

    async def get_source(*args: object, **kwargs: object) -> SimpleNamespace | None:
        session.transaction_open = True
        return source

    async def lock_source(*args: object, **kwargs: object) -> SimpleNamespace:
        session.transaction_open = True
        return locked_source

    async def get_version(*args: object, **kwargs: object) -> SimpleNamespace | None:
        session.transaction_open = True
        return existing_version

    candidate = SimpleNamespace(id=12, source_id=9, synced_at=None)
    mocks = {
        "get_or_create_doc_source": AsyncMock(side_effect=get_or_create),
        "get_doc_source_by_identity": AsyncMock(side_effect=get_source),
        "get_active_source_version": AsyncMock(side_effect=get_active),
        "get_doc_source_for_update": AsyncMock(side_effect=lock_source),
        "get_source_version_by_commit": AsyncMock(side_effect=get_version),
        "create_source_version_with_documents": AsyncMock(return_value=candidate),
        "promote_source_version": AsyncMock(),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(pipeline, name, mock, raising=False)
    return mocks


async def ingest(
    session: FakeSession, embeddings: FakeEmbeddings
) -> pipeline.GithubIngestionResult:
    return await pipeline.ingest_github_repository(
        session,
        settings=make_settings(),
        embeddings=embeddings,
        repo_url="https://github.com/example/project",
        branch=None,
        path="docs",
        max_files=50,
    )


@pytest.mark.asyncio
async def test_preliminary_no_op_closes_read_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    github = install_github(monkeypatch, session)
    active = SimpleNamespace(id=11, source_id=9, commit_sha=COMMIT_SHA)
    install_repositories(
        monkeypatch,
        session,
        observed_active=active,
        locked_source=SimpleNamespace(id=9, active_version_id=11),
        locked_active=active,
    )

    result = await ingest(session, FakeEmbeddings(session))

    assert result.status == "no_op"
    assert session.transaction_open is False
    assert session.commits == 0
    assert session.rollbacks == 1
    github.fetch_markdown_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_preparation_runs_without_database_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    install_github(monkeypatch, session)
    old_active = SimpleNamespace(id=10, source_id=9, commit_sha=OTHER_SHA)
    mocks = install_repositories(
        monkeypatch,
        session,
        observed_active=old_active,
        locked_source=SimpleNamespace(id=9, active_version_id=10),
        locked_active=old_active,
    )

    result = await ingest(session, FakeEmbeddings(session))

    assert result.status == "synchronized"
    assert session.commits == 1
    assert session.rollbacks == 1
    mocks["create_source_version_with_documents"].assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_markdown_source_is_rejected_before_source_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    github = install_github(monkeypatch, session, files=[])
    mocks = install_repositories(
        monkeypatch,
        session,
        observed_active=None,
        locked_source=SimpleNamespace(id=9, active_version_id=None),
        locked_active=None,
        source_exists=False,
    )
    embeddings = FakeEmbeddings(session)

    with pytest.raises(ValueError, match="No indexable Markdown content"):
        await ingest(session, embeddings)

    github.close.assert_awaited_once()
    embeddings.embed_texts.assert_not_awaited()
    mocks["get_or_create_doc_source"].assert_not_awaited()
    assert session.commits == 0


@pytest.mark.asyncio
async def test_same_sha_promoted_during_preparation_returns_no_op(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    old_active = SimpleNamespace(id=10, source_id=9, commit_sha=OTHER_SHA)
    new_active = SimpleNamespace(id=13, source_id=9, commit_sha=COMMIT_SHA)
    locked_source = SimpleNamespace(id=9, active_version_id=13)
    install_github(monkeypatch, session)
    mocks = install_repositories(
        monkeypatch,
        session,
        observed_active=old_active,
        locked_source=locked_source,
        locked_active=new_active,
    )

    result = await ingest(session, FakeEmbeddings(session))

    assert result.status == "no_op"
    assert result.source_version_id == 13
    assert session.transaction_open is False
    assert session.commits == 0
    assert session.rollbacks == 2
    mocks["create_source_version_with_documents"].assert_not_awaited()
    mocks["promote_source_version"].assert_not_awaited()


@pytest.mark.asyncio
async def test_different_active_version_promoted_during_preparation_raises_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    old_active = SimpleNamespace(id=10, source_id=9, commit_sha=OTHER_SHA)
    newer_active = SimpleNamespace(id=14, source_id=9, commit_sha="d" * 40)
    install_github(monkeypatch, session)
    mocks = install_repositories(
        monkeypatch,
        session,
        observed_active=old_active,
        locked_source=SimpleNamespace(id=9, active_version_id=14),
        locked_active=newer_active,
    )

    with pytest.raises(pipeline.SourceSynchronizationConflict):
        await ingest(session, FakeEmbeddings(session))

    assert session.transaction_open is False
    assert session.commits == 0
    assert session.rollbacks == 2
    mocks["create_source_version_with_documents"].assert_not_awaited()
    mocks["promote_source_version"].assert_not_awaited()


@pytest.mark.asyncio
async def test_retained_same_sha_is_reused_without_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    old_active = SimpleNamespace(id=10, source_id=9, commit_sha=OTHER_SHA)
    retained = SimpleNamespace(id=8, source_id=9, commit_sha=COMMIT_SHA, synced_at=None)
    install_github(monkeypatch, session)
    mocks = install_repositories(
        monkeypatch,
        session,
        observed_active=old_active,
        locked_source=SimpleNamespace(id=9, active_version_id=10),
        locked_active=old_active,
        existing_version=retained,
    )

    result = await ingest(session, FakeEmbeddings(session))

    assert result.status == "synchronized"
    assert result.source_version_id == 8
    mocks["create_source_version_with_documents"].assert_not_awaited()
    assert mocks["promote_source_version"].await_args.kwargs["version"] is retained
    assert session.commits == 1
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_final_persistence_failure_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    old_active = SimpleNamespace(id=10, source_id=9, commit_sha=OTHER_SHA)
    install_github(monkeypatch, session)
    mocks = install_repositories(
        monkeypatch,
        session,
        observed_active=old_active,
        locked_source=SimpleNamespace(id=9, active_version_id=10),
        locked_active=old_active,
    )
    mocks["promote_source_version"].side_effect = RuntimeError("database failure")

    with pytest.raises(RuntimeError, match="database failure"):
        await ingest(session, FakeEmbeddings(session))

    assert session.commits == 0
    assert session.rollbacks == 2
    assert session.transaction_open is False


@pytest.mark.asyncio
async def test_missing_source_is_not_created_when_embedding_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    install_github(monkeypatch, session)
    mocks = install_repositories(
        monkeypatch,
        session,
        observed_active=None,
        locked_source=SimpleNamespace(id=9, active_version_id=None),
        locked_active=None,
        source_exists=False,
    )

    with pytest.raises(RuntimeError, match="embedding failure"):
        await ingest(session, FailingEmbeddings(session))

    assert session.commits == 0
    assert session.transaction_open is False
    mocks["get_or_create_doc_source"].assert_not_awaited()
