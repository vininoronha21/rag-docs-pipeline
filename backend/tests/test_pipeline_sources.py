from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import pipeline

COMMIT_SHA = "a" * 40


class FakeSession:
    def __init__(self, *, active_version_id: int | None = None) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.active_version_id = active_version_id
        self.previous_active_version_id = active_version_id

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.active_version_id = self.previous_active_version_id


class FakeEmbeddings:
    dimensions = 2

    def __init__(self) -> None:
        self.embed_texts = AsyncMock(return_value=[[1.0, 0.0]])


def make_settings() -> SimpleNamespace:
    return SimpleNamespace(
        embedding_provider="local",
        embedding_dimensions=2,
        openai_embedding_model="text-embedding-3-small",
    )


def install_github(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    github = SimpleNamespace(
        get_repo=AsyncMock(
            return_value=SimpleNamespace(full_name="example/project", default_branch="main")
        ),
        resolve_commit=AsyncMock(return_value=COMMIT_SHA),
        fetch_markdown_files=AsyncMock(
            return_value=[
                SimpleNamespace(
                    path="docs/index.md",
                    html_url=f"https://github.com/example/project/blob/{COMMIT_SHA}/docs/index.md",
                    sha="b" * 40,
                    content="# Install\n\nRun the server.",
                )
            ]
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr(pipeline, "GithubClient", lambda _settings: github)
    return github


@pytest.mark.asyncio
async def test_same_active_commit_is_no_op_before_fetch_or_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github = install_github(monkeypatch)
    session = FakeSession(active_version_id=11)
    embeddings = FakeEmbeddings()
    source = SimpleNamespace(id=9, active_version_id=11)
    active = SimpleNamespace(id=11, source_id=9, commit_sha=COMMIT_SHA)
    monkeypatch.setattr(pipeline, "get_or_create_doc_source", AsyncMock(return_value=source))
    monkeypatch.setattr(pipeline, "get_active_source_version", AsyncMock(return_value=active))

    result = await pipeline.ingest_github_repository(
        session,
        settings=make_settings(),
        embeddings=embeddings,
        repo_url="https://github.com/example/project",
        branch=None,
        path="docs",
        max_files=50,
    )

    assert result.status == "no_op"
    assert result.commit_sha == COMMIT_SHA
    assert result.source_id == 9
    assert result.source_version_id == 11
    assert result.documents == []
    github.resolve_commit.assert_awaited_once_with(github.get_repo.return_value, branch="main")
    github.fetch_markdown_files.assert_not_awaited()
    embeddings.embed_texts.assert_not_awaited()
    assert session.commits == 0
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_ingestion_builds_candidate_and_commits_promotion_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    github = install_github(monkeypatch)
    session = FakeSession(active_version_id=10)
    embeddings = FakeEmbeddings()
    source = SimpleNamespace(id=9, active_version_id=10, last_sync=None)
    candidate = SimpleNamespace(id=12, source_id=9)
    create_candidate = AsyncMock(return_value=candidate)

    async def promote(
        _session: object, *, source: SimpleNamespace, version: SimpleNamespace, retention: int
    ) -> None:
        assert version is candidate
        assert retention == 5
        source.active_version_id = version.id
        session.active_version_id = version.id

    monkeypatch.setattr(pipeline, "get_or_create_doc_source", AsyncMock(return_value=source))
    monkeypatch.setattr(pipeline, "get_active_source_version", AsyncMock(return_value=None))
    monkeypatch.setattr(pipeline, "create_source_version_with_documents", create_candidate)
    monkeypatch.setattr(pipeline, "promote_source_version", promote)

    result = await pipeline.ingest_github_repository(
        session,
        settings=make_settings(),
        embeddings=embeddings,
        repo_url="https://github.com/example/project",
        branch=None,
        path="docs",
        max_files=50,
    )

    assert result.status == "synchronized"
    assert result.branch == "main"
    assert result.path == "docs"
    assert result.source_version_id == 12
    assert [document.source_url for document in result.documents] == [
        f"https://github.com/example/project/blob/{COMMIT_SHA}/docs/index.md"
    ]
    github.fetch_markdown_files.assert_awaited_once_with(
        github.get_repo.return_value,
        commit_sha=COMMIT_SHA,
        path="docs",
        max_files=50,
    )
    candidate_documents = create_candidate.await_args.kwargs["documents"]
    assert [document.repository_path for document in candidate_documents] == ["docs/index.md"]
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_ingestion_rolls_back_failed_promotion_and_preserves_previous_active_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_github(monkeypatch)
    session = FakeSession(active_version_id=10)
    source = SimpleNamespace(id=9, active_version_id=10, last_sync=None)
    candidate = SimpleNamespace(id=12, source_id=9)

    async def failing_promote(*args: object, **kwargs: object) -> None:
        source.active_version_id = candidate.id
        session.active_version_id = candidate.id
        raise RuntimeError("database failure")

    monkeypatch.setattr(pipeline, "get_or_create_doc_source", AsyncMock(return_value=source))
    monkeypatch.setattr(pipeline, "get_active_source_version", AsyncMock(return_value=None))
    monkeypatch.setattr(
        pipeline, "create_source_version_with_documents", AsyncMock(return_value=candidate)
    )
    monkeypatch.setattr(pipeline, "promote_source_version", failing_promote)

    with pytest.raises(RuntimeError, match="database failure"):
        await pipeline.ingest_github_repository(
            session,
            settings=make_settings(),
            embeddings=FakeEmbeddings(),
            repo_url="https://github.com/example/project",
            branch="main",
            path="docs",
            max_files=50,
        )

    assert session.rollbacks == 1
    assert session.commits == 0
    assert session.active_version_id == 10
