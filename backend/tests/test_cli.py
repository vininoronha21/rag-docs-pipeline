from types import SimpleNamespace
from typing import Literal
from uuid import UUID

import pytest
import typer
from typer.testing import CliRunner

from app import cli as cli_module
from app.services.pipeline import GithubIngestionResult, IngestedDocumentResult
from app.services.querying import QueryExecutionMetrics, QueryExecutionResult
from app.services.rag import CitedSentence, ExtractiveAnswer


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.parametrize("arguments", [[], [""]])
def test_cli_ingest_requires_non_empty_path(arguments: list[str]) -> None:
    result = CliRunner().invoke(
        cli_module.cli,
        ["ingest-github", "https://github.com/example/project", *arguments],
    )

    assert result.exit_code == 2
    assert "PATH" in result.output


@pytest.mark.parametrize("status", ["synchronized", "no_op"])
def test_cli_ingest_reports_complete_result(
    monkeypatch: pytest.MonkeyPatch,
    status: Literal["synchronized", "no_op"],
) -> None:
    session = FakeSession()
    settings = object()
    embeddings = object()
    output: list[str] = []

    async def fake_ingest_github_repository(
        *args: object, **kwargs: object
    ) -> GithubIngestionResult:
        assert args == (session,)
        assert kwargs == {
            "settings": settings,
            "embeddings": embeddings,
            "repo_url": "https://github.com/example/project",
            "branch": None,
            "path": "docs",
            "max_files": 50,
        }
        documents = (
            [
                IngestedDocumentResult(
                    source_url="https://github.com/example/project/blob/main/docs/index.md",
                    title="Project docs",
                    chunk_count=4,
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

    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    monkeypatch.setattr(cli_module, "build_embedding_provider", lambda _settings: embeddings)
    monkeypatch.setattr(cli_module, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(cli_module, "ingest_github_repository", fake_ingest_github_repository)
    monkeypatch.setattr(cli_module.console, "print", lambda message: output.append(str(message)))

    cli_module.ingest_github("https://github.com/example/project", "docs")

    rendered = "\n".join(output)
    if status == "no_op":
        assert "No changes" in rendered
        assert "Documents: none" in rendered
    else:
        assert "Synchronized" in rendered
        assert "https://github.com/example/project/blob/main/docs/index.md" in rendered
        assert "Project docs" in rendered
        assert "4 chunks" in rendered
    assert "Branch: main" in rendered
    assert "Path: docs" in rendered
    assert "Source ID: 3" in rendered
    assert "a" * 40 in rendered
    assert "Version: 7" in rendered


@pytest.mark.parametrize("max_files", [0, 501])
def test_cli_ingest_rejects_max_files_outside_api_bounds(
    monkeypatch: pytest.MonkeyPatch,
    max_files: int,
) -> None:
    async def unexpected_ingest(*args: object, **kwargs: object) -> None:
        raise AssertionError("ingestion must not run")

    monkeypatch.setattr(cli_module, "get_settings", lambda: object())
    monkeypatch.setattr(cli_module, "build_embedding_provider", lambda _settings: object())
    monkeypatch.setattr(cli_module, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(cli_module, "ingest_github_repository", unexpected_ingest)

    result = CliRunner().invoke(
        cli_module.cli,
        [
            "ingest-github",
            "https://github.com/example/project",
            "docs",
            "--max-files",
            str(max_files),
        ],
    )

    assert result.exit_code == 2
    assert "max-files" in result.output.lower()


@pytest.mark.asyncio
async def test_cli_query_filters_logs_and_returns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeSession()
    settings = SimpleNamespace(retrieval_min_score=0.1)
    embeddings = object()

    async def fake_run_query(*args: object, **kwargs: object) -> QueryExecutionResult:
        assert args == (session,)
        assert kwargs == {
            "question": "How do I run FastAPI?",
            "top_k": 5,
            "source": "github",
            "settings": settings,
            "embeddings": embeddings,
        }
        return QueryExecutionResult(
            event_id=UUID("2be66d42-8f42-4e9d-aa38-51b514607c38"),
            state="answered",
            answer=ExtractiveAnswer(
                sentences=[
                    CitedSentence(
                        text="FastAPI runs with Uvicorn from the command line.", chunk_id=3
                    )
                ]
            ),
            evidence=[],
            metrics=QueryExecutionMetrics(
                latency_ms=15,
                retrieved_chunk_count=1,
                top_fused_score=0.02,
                score_gap=None,
            ),
        )

    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    monkeypatch.setattr(cli_module, "build_embedding_provider", lambda _settings: embeddings)
    monkeypatch.setattr(cli_module, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(cli_module, "run_query", fake_run_query)

    result = await cli_module._run_query(
        "How do I run FastAPI?",
        top_k=5,
        source="github",
    )

    assert result.answer is not None
    assert "FastAPI runs with Uvicorn" in result.answer.sentences[0].text
    assert str(result.event_id) == "2be66d42-8f42-4e9d-aa38-51b514607c38"
    assert result.metrics.retrieved_chunk_count == 1


def test_cli_query_returns_bad_parameter_for_invalid_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_query(*args: object, **kwargs: object) -> tuple[str, int, int, int]:
        raise ValueError("Question must contain at least two non-whitespace characters.")

    monkeypatch.setattr(cli_module, "_run_query", fake_run_query)

    with pytest.raises(typer.BadParameter) as exc_info:
        cli_module.query(" ", top_k=5)

    assert "at least two" in str(exc_info.value)


def test_cli_query_renders_insufficient_state_without_fabricated_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_query(*args: object, **kwargs: object) -> QueryExecutionResult:
        return QueryExecutionResult(
            event_id=UUID("2be66d42-8f42-4e9d-aa38-51b514607c38"),
            state="insufficient_evidence",
            answer=None,
            evidence=[],
            metrics=QueryExecutionMetrics(
                latency_ms=15,
                retrieved_chunk_count=0,
                top_fused_score=None,
                score_gap=None,
            ),
        )

    monkeypatch.setattr(cli_module, "_run_query", fake_run_query)

    result = CliRunner().invoke(cli_module.cli, ["query", "unknown topic"])

    assert result.exit_code == 0
    assert "Insufficient evidence" in result.output
    assert "None" not in result.output
    assert "insufficient_evidence" in result.output
