from types import SimpleNamespace
from typing import Any, Literal

import pytest
from scripts import verify_pipeline

from app.db.models import DocSource, SourceVersion
from app.services.pipeline import GithubIngestionResult, IngestedDocumentResult


class ScalarResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one(self) -> Any:
        return self.value

    def scalar_one_or_none(self) -> Any:
        return self.value

    def all(self) -> list[Any]:
        return list(self.value)


class FakeSession:
    def __init__(
        self,
        *,
        objects: dict[type[Any], Any] | None = None,
        documents: list[Any] | None = None,
        chunk_count: int = 0,
    ) -> None:
        self.objects = objects or {}
        self.documents = documents or []
        self.chunk_count = chunk_count
        self.requested_ids: list[tuple[type[Any], int]] = []

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def get(self, model: type[Any], object_id: int) -> Any:
        self.requested_ids.append((model, object_id))
        return self.objects.get(model)

    async def scalars(self, statement: object) -> ScalarResult:
        return ScalarResult(self.documents)

    async def scalar(self, statement: object) -> int:
        return self.chunk_count

    async def commit(self) -> None:
        pass


def ingestion_result(
    status: Literal["synchronized", "no_op"] = "synchronized",
) -> GithubIngestionResult:
    documents = (
        [
            IngestedDocumentResult(
                source_url="https://github.com/example/project/blob/main/docs/index.md",
                title="Docs",
                chunk_count=2,
            )
        ]
        if status == "synchronized"
        else []
    )
    return GithubIngestionResult(
        status=status,
        repository="example/project",
        branch="main",
        path="docs",
        commit_sha="a" * 40,
        source_id=3,
        source_version_id=7,
        documents=documents,
    )


def target_session(*, enabled: bool = True) -> FakeSession:
    source = SimpleNamespace(
        id=3,
        repository="example/project",
        branch="main",
        path="docs",
        active_version_id=7,
        enabled=enabled,
    )
    version = SimpleNamespace(
        id=7,
        source_id=3,
        commit_sha="a" * 40,
        document_count=1,
        chunk_count=2,
    )
    document = SimpleNamespace(id=11, source_version_id=7)
    return FakeSession(
        objects={DocSource: source, SourceVersion: version},
        documents=[document],
        chunk_count=2,
    )


@pytest.mark.asyncio
async def test_verify_persistence_validates_only_ingestion_result_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = target_session()
    monkeypatch.setattr(verify_pipeline, "AsyncSessionLocal", lambda: session)

    ok, counts = await verify_pipeline.verify_persistence(ingestion_result())

    assert ok is True
    assert counts == {"documents": 1, "document_chunks": 2}
    assert session.requested_ids == [(DocSource, 3), (SourceVersion, 7)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("invalid_field", "invalid_value"),
    [
        ("version_source_id", 99),
        ("active_version_id", 99),
        ("document_owner", 99),
        ("version_document_count", 2),
        ("version_chunk_count", 3),
    ],
)
async def test_verify_persistence_rejects_target_integrity_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    invalid_field: str,
    invalid_value: int,
) -> None:
    session = target_session()
    source = session.objects[DocSource]
    version = session.objects[SourceVersion]
    if invalid_field == "version_source_id":
        version.source_id = invalid_value
    elif invalid_field == "active_version_id":
        source.active_version_id = invalid_value
    elif invalid_field == "document_owner":
        session.documents[0].source_version_id = invalid_value
    elif invalid_field == "version_document_count":
        version.document_count = invalid_value
    else:
        version.chunk_count = invalid_value
    monkeypatch.setattr(verify_pipeline, "AsyncSessionLocal", lambda: session)

    ok, _counts = await verify_pipeline.verify_persistence(ingestion_result())

    assert ok is False


@pytest.mark.asyncio
async def test_verify_ingest_requires_no_op_with_same_target_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    persisted: list[GithubIngestionResult] = []
    first = ingestion_result()
    second = ingestion_result("no_op")

    async def fake_ingest(*args: object, **kwargs: object) -> GithubIngestionResult:
        calls.append(kwargs)
        return first if len(calls) == 1 else second

    async def fake_verify_persistence(
        result: GithubIngestionResult,
    ) -> tuple[bool, dict[str, int]]:
        persisted.append(result)
        return True, {"documents": 1, "document_chunks": 2}

    monkeypatch.setattr(verify_pipeline, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(verify_pipeline, "ingest_github_repository", fake_ingest)
    monkeypatch.setattr(verify_pipeline, "verify_persistence", fake_verify_persistence)

    ok, target = await verify_pipeline.verify_ingest(object(), object())

    assert ok is True
    assert target is second
    assert persisted == [first, second]
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_verify_ingest_rejects_no_op_count_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    first = ingestion_result()
    second = ingestion_result("no_op")
    results = iter([first, second])
    counts = iter(
        [
            (True, {"documents": 1, "document_chunks": 2}),
            (True, {"documents": 1, "document_chunks": 1}),
        ]
    )

    async def fake_ingest(*args: object, **kwargs: object) -> GithubIngestionResult:
        return next(results)

    async def fake_verify_persistence(
        result: GithubIngestionResult,
    ) -> tuple[bool, dict[str, int]]:
        return next(counts)

    monkeypatch.setattr(verify_pipeline, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(verify_pipeline, "ingest_github_repository", fake_ingest)
    monkeypatch.setattr(verify_pipeline, "verify_persistence", fake_verify_persistence)

    ok, target = await verify_pipeline.verify_ingest(object(), object())

    assert ok is False
    assert target is None


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_enabled", [True, False])
async def test_verify_source_disable_is_source_specific_and_restores_exact_state(
    monkeypatch: pytest.MonkeyPatch,
    previous_enabled: bool,
) -> None:
    session = target_session(enabled=previous_enabled)
    source = session.objects[DocSource]
    query_source_ids: list[int | None] = []

    async def fake_run_query(*args: object, **kwargs: object) -> SimpleNamespace:
        query_source_ids.append(kwargs.get("source_id"))
        return SimpleNamespace(retrieved_chunk_count=0)

    monkeypatch.setattr(verify_pipeline, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(verify_pipeline, "run_query", fake_run_query)

    ok = await verify_pipeline.verify_source_disable(
        object(),
        object(),
        ingestion_result(),
    )

    assert ok is True
    assert query_source_ids == [3]
    assert source.enabled is previous_enabled
    assert session.requested_ids == [(DocSource, 3), (DocSource, 3)]


@pytest.mark.asyncio
async def test_verify_source_disable_restores_state_when_query_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = target_session(enabled=True)
    source = session.objects[DocSource]

    async def fake_run_query(*args: object, **kwargs: object) -> None:
        assert kwargs["source_id"] == 3
        raise RuntimeError("query failed")

    monkeypatch.setattr(verify_pipeline, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(verify_pipeline, "run_query", fake_run_query)

    assert (
        await verify_pipeline.verify_source_disable(
            object(),
            object(),
            ingestion_result(),
        )
        is False
    )
    assert source.enabled is True
