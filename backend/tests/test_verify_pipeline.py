from types import SimpleNamespace
from typing import Any, Literal
from uuid import uuid4

import pytest

from app.db.models import DocSource, QueryEvent, SourceVersion
from app.services.pipeline import GithubIngestionResult, IngestedDocumentResult
from scripts import verify_pipeline


class ScalarResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one(self) -> Any:
        return self.value

    def scalar_one_or_none(self) -> Any:
        return self.value

    def all(self) -> list[Any]:
        return list(self.value)


class TableResult:
    def __init__(self, tables: set[str]) -> None:
        self.tables = tables

    def fetchall(self) -> list[tuple[str]]:
        return [(table,) for table in self.tables]


class FakeSession:
    def __init__(
        self,
        *,
        objects: dict[type[Any], Any] | None = None,
        documents: list[Any] | None = None,
        chunk_count: int = 0,
        tables: set[str] | None = None,
    ) -> None:
        self.objects = objects or {}
        self.documents = documents or []
        self.chunk_count = chunk_count
        self.tables = tables or set()
        self.requested_ids: list[tuple[type[Any], Any]] = []

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def get(self, model: type[Any], object_id: Any) -> Any:
        self.requested_ids.append((model, object_id))
        return self.objects.get(model)

    async def scalars(self, statement: object) -> ScalarResult:
        return ScalarResult(self.documents)

    async def execute(self, statement: object) -> TableResult:
        return TableResult(self.tables)

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


def anonymous_event(event_id: Any, **overrides: Any) -> SimpleNamespace:
    fields = {
        "id": event_id,
        "state": "answered",
        "latency_ms": 1,
        "retrieved_chunk_count": 1,
        "source_ids": [3],
        "source_version_ids": [7],
        "top_fused_score": 0.91,
        "score_gap": 0.2,
        "feedback": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def answered_query_result(event_id: Any, **overrides: Any) -> SimpleNamespace:
    commit_sha = "a" * 40
    fields = {
        "event_id": event_id,
        "state": "answered",
        "answer": SimpleNamespace(
            sentences=[SimpleNamespace(text="Use fastapi dev with the application path.")]
        ),
        "evidence": [
            SimpleNamespace(
                citation_id="citation-1",
                supported_text="Use fastapi dev with the application path.",
                excerpt="fastapi dev main.py starts the local development server.",
                title="Primeiros passos",
                repository_path="docs/pt/docs/tutorial/first-steps.md",
                section="`fastapi dev` com path ou com a opção de CLI `--entrypoint`",
                commit_sha=commit_sha,
                source_url=(
                    "https://github.com/example/project/blob/"
                    f"{commit_sha}/docs/pt/docs/tutorial/first-steps.md"
                ),
                vector_score=0.88,
                text_score=0.74,
                fused_score=0.91,
            )
        ],
        "metrics": SimpleNamespace(
            retrieved_chunk_count=1,
            latency_ms=1,
            top_fused_score=0.91,
            score_gap=0.2,
        ),
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


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


def test_verifier_targets_portfolio_pt_br_demo_corpus() -> None:
    assert verify_pipeline.VERIFY_REPO_URL == "https://github.com/fastapi/fastapi"
    assert getattr(verify_pipeline, "VERIFY_BRANCH", None) == "master"
    assert verify_pipeline.VERIFY_PATH == "docs/pt/docs"
    assert "fastapi dev" in verify_pipeline.VERIFY_QUESTION


@pytest.mark.asyncio
async def test_verify_tables_exist_uses_anonymous_query_events_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession(
        tables={
            "documents",
            "document_chunks",
            "doc_sources",
            "source_versions",
            "query_events",
            "alembic_version",
        }
    )
    monkeypatch.setattr(verify_pipeline, "AsyncSessionLocal", lambda: session)

    assert await verify_pipeline.verify_tables_exist() is True


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
async def test_verify_persistence_rejects_disabled_target_with_other_enabled_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = target_session(enabled=False)
    session.unrelated_source = SimpleNamespace(id=99, source_type="github", enabled=True)
    monkeypatch.setattr(verify_pipeline, "AsyncSessionLocal", lambda: session)

    ok, _counts = await verify_pipeline.verify_persistence(ingestion_result())

    assert ok is False


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

    settings = object()
    embeddings = object()

    ok, target = await verify_pipeline.verify_ingest(settings, embeddings)

    assert ok is True
    assert target is second
    assert persisted == [first, second]
    assert calls == [
        {
            "settings": settings,
            "embeddings": embeddings,
            "repo_url": "https://github.com/fastapi/fastapi",
            "branch": "master",
            "path": "docs/pt/docs",
            "max_files": verify_pipeline.VERIFY_MAX_FILES,
        },
        {
            "settings": settings,
            "embeddings": embeddings,
            "repo_url": "https://github.com/fastapi/fastapi",
            "branch": "master",
            "path": "docs/pt/docs",
            "max_files": verify_pipeline.VERIFY_MAX_FILES,
        },
    ]


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
async def test_verify_query_cannot_use_another_enabled_github_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_ids: list[int | None] = []

    async def fake_run_query(*args: object, **kwargs: object) -> SimpleNamespace:
        source_id = kwargs.get("source_id")
        source_ids.append(source_id)
        if source_id == 3:
            return SimpleNamespace(
                answer=None,
                metrics=SimpleNamespace(retrieved_chunk_count=0, latency_ms=1),
                event_id=uuid4(),
            )
        return SimpleNamespace(
            answer=SimpleNamespace(sentences=[SimpleNamespace(text="Unrelated answer")]),
            metrics=SimpleNamespace(retrieved_chunk_count=1, latency_ms=1),
            event_id=uuid4(),
        )

    monkeypatch.setattr(verify_pipeline, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(verify_pipeline, "run_query", fake_run_query)

    ok = await verify_pipeline.verify_query(
        object(),
        object(),
        ingestion_result(),
    )

    assert ok is False
    assert source_ids == [3]


@pytest.mark.asyncio
async def test_verify_query_proves_positive_retrieval_for_target_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_id = uuid4()
    session = FakeSession(objects={QueryEvent: anonymous_event(event_id)})

    async def fake_run_query(*args: object, **kwargs: object) -> SimpleNamespace:
        assert kwargs["source_id"] == 3
        return answered_query_result(event_id)

    monkeypatch.setattr(verify_pipeline, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(verify_pipeline, "run_query", fake_run_query)

    assert (
        await verify_pipeline.verify_query(
            object(),
            object(),
            ingestion_result(),
        )
        is True
    )
    assert (QueryEvent, event_id) in session.requested_ids


@pytest.mark.asyncio
async def test_verify_query_rejects_query_event_with_visitor_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_id = uuid4()
    event = anonymous_event(event_id)
    event.question = "How do I run this?"
    session = FakeSession(objects={QueryEvent: event})

    async def fake_run_query(*args: object, **kwargs: object) -> SimpleNamespace:
        return answered_query_result(event_id)

    monkeypatch.setattr(verify_pipeline, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(verify_pipeline, "run_query", fake_run_query)

    assert await verify_pipeline.verify_query(object(), object(), ingestion_result()) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("citation_id", None),
        ("supported_text", ""),
        ("commit_sha", "main"),
        (
            "source_url",
            "https://github.com/example/project/blob/main/docs/pt/docs/tutorial/first-steps.md",
        ),
        ("repository_path", "other/tutorial/first-steps.md"),
    ],
)
async def test_verify_query_requires_commit_pinned_answer_evidence(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    event_id = uuid4()
    session = FakeSession(objects={QueryEvent: anonymous_event(event_id)})

    async def fake_run_query(*args: object, **kwargs: object) -> SimpleNamespace:
        result = answered_query_result(event_id)
        setattr(result.evidence[0], field, value)
        return result

    monkeypatch.setattr(verify_pipeline, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(verify_pipeline, "run_query", fake_run_query)

    assert await verify_pipeline.verify_query(object(), object(), ingestion_result()) is False


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
        return SimpleNamespace(metrics=SimpleNamespace(retrieved_chunk_count=0))

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
