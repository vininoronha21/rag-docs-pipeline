from types import SimpleNamespace
from typing import Any

import pytest
from scripts import verify_pipeline

from app.services.pipeline import GithubIngestionResult, IngestedDocumentResult


class ScalarResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one(self) -> Any:
        return self.value

    def scalar_one_or_none(self) -> Any:
        return self.value


class FakeSession:
    def __init__(self, *, source: Any = None, statements: list[str] | None = None) -> None:
        self.source = source
        self.statements = statements

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def execute(self, statement: object) -> ScalarResult:
        if self.statements is not None:
            self.statements.append(str(statement))
            return ScalarResult(1)
        return ScalarResult(self.source)

    async def get(self, model: object, source_id: int) -> Any:
        return self.source

    async def commit(self) -> None:
        pass


@pytest.mark.asyncio
async def test_verify_ingest_requires_second_sync_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    first = GithubIngestionResult(
        status="synchronized",
        repository="example/project",
        branch="main",
        path="docs",
        commit_sha="a" * 40,
        source_id=3,
        source_version_id=7,
        documents=[
            IngestedDocumentResult(
                source_url="https://github.com/example/project/blob/main/docs/index.md",
                title="Docs",
                chunk_count=2,
            )
        ],
    )
    second = GithubIngestionResult(
        status="no_op",
        repository="example/project",
        branch="main",
        path="docs",
        commit_sha="a" * 40,
        source_id=3,
        source_version_id=7,
        documents=[],
    )

    async def fake_ingest(*args: object, **kwargs: object) -> GithubIngestionResult:
        calls.append(kwargs)
        return first if len(calls) == 1 else second

    monkeypatch.setattr(verify_pipeline, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(verify_pipeline, "ingest_github_repository", fake_ingest)

    ok, doc_count, chunk_count = await verify_pipeline.verify_ingest(object(), object())

    assert ok is True
    assert (doc_count, chunk_count) == (1, 2)
    assert len(calls) == 2
    assert calls[0]["path"]


@pytest.mark.asyncio
async def test_verify_persistence_checks_versions_ownership_and_active_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements: list[str] = []
    monkeypatch.setattr(
        verify_pipeline,
        "AsyncSessionLocal",
        lambda: FakeSession(statements=statements),
    )

    ok, counts = await verify_pipeline.verify_persistence()

    sql = "\n".join(statements)
    assert ok is True
    assert counts["source_versions"] == 1
    assert "JOIN source_versions" in sql
    assert "JOIN doc_sources" in sql
    assert "active_version_id" in sql


@pytest.mark.asyncio
async def test_verify_source_disable_restores_state_when_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = SimpleNamespace(id=3, enabled=True)

    async def fake_run_query(*args: object, **kwargs: object) -> None:
        raise RuntimeError("query failed")

    monkeypatch.setattr(verify_pipeline, "AsyncSessionLocal", lambda: FakeSession(source=source))
    monkeypatch.setattr(verify_pipeline, "run_query", fake_run_query)

    assert await verify_pipeline.verify_source_disable(object(), object()) is False
    assert source.enabled is True
