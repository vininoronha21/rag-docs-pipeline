import httpx
import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.api import routes
from app.schemas import GithubIngestRequest, IngestResponse
from app.services.embeddings import EmbeddingProviderError
from app.services.github import GithubClientError
from app.services.pipeline import (
    GithubIngestionResult,
    SourceSynchronizationConflict,
)


def ingest_payload() -> GithubIngestRequest:
    return GithubIngestRequest(
        repo_url="https://github.com/example/project",
        path="docs",
        max_files=1,
    )


@pytest.mark.parametrize("payload", [{}, {"path": ""}])
def test_ingest_schema_requires_non_empty_path(payload: dict[str, str]) -> None:
    app = FastAPI()

    @app.post("/ingest")
    async def ingest(request: GithubIngestRequest) -> GithubIngestRequest:
        return request

    response = TestClient(app).post(
        "/ingest",
        json={"repo_url": "https://github.com/example/project", **payload},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_ingest_response_serializes_no_op_version() -> None:
    response = IngestResponse(
        status="no_op",
        repository="example/project",
        branch="main",
        path="docs",
        commit_sha="a" * 40,
        source_id=3,
        source_version_id=7,
        documents=[],
        total_chunks=0,
    )

    assert response.model_dump() == {
        "status": "no_op",
        "repository": "example/project",
        "branch": "main",
        "path": "docs",
        "commit_sha": "a" * 40,
        "source_id": 3,
        "source_version_id": 7,
        "documents": [],
        "total_chunks": 0,
    }


@pytest.mark.asyncio
async def test_ingest_github_returns_complete_versioned_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ingest_github_repository(
        *args: object, **kwargs: object
    ) -> GithubIngestionResult:
        return GithubIngestionResult(
            status="no_op",
            repository="example/project",
            branch="main",
            path="docs",
            commit_sha="a" * 40,
            source_id=3,
            source_version_id=7,
            documents=[],
        )

    monkeypatch.setattr(routes, "ingest_github_repository", fake_ingest_github_repository)

    response = await routes.ingest_github(
        ingest_payload(),
        session=object(),
        settings=object(),
        embeddings=object(),
    )

    assert response.model_dump() == {
        "status": "no_op",
        "repository": "example/project",
        "branch": "main",
        "path": "docs",
        "commit_sha": "a" * 40,
        "source_id": 3,
        "source_version_id": 7,
        "documents": [],
        "total_chunks": 0,
    }


@pytest.mark.asyncio
async def test_ingest_github_returns_conflict_for_competing_promotion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ingest_github_repository(*args: object, **kwargs: object) -> None:
        raise SourceSynchronizationConflict("internal synchronization details")

    monkeypatch.setattr(routes, "ingest_github_repository", fake_ingest_github_repository)

    with pytest.raises(HTTPException) as exc_info:
        await routes.ingest_github(
            ingest_payload(),
            session=object(),
            settings=object(),
            embeddings=object(),
        )

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "Source changed during synchronization. Retry the request."


@pytest.mark.asyncio
async def test_ingest_github_returns_bad_request_for_invalid_repo_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ingest_github_repository(*args: object, **kwargs: object) -> None:
        raise ValueError("Expected a GitHub repository URL like https://github.com/owner/repo")

    monkeypatch.setattr(routes, "ingest_github_repository", fake_ingest_github_repository)

    with pytest.raises(HTTPException) as exc_info:
        await routes.ingest_github(
            ingest_payload(),
            session=object(),
            settings=object(),
            embeddings=object(),
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Expected a GitHub repository URL" in exc_info.value.detail


@pytest.mark.asyncio
async def test_ingest_github_returns_not_found_for_missing_github_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("GET", "https://api.github.com/repos/example/project")
    response = httpx.Response(status.HTTP_404_NOT_FOUND, request=request)

    async def fake_ingest_github_repository(*args: object, **kwargs: object) -> None:
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(routes, "ingest_github_repository", fake_ingest_github_repository)

    with pytest.raises(HTTPException) as exc_info:
        await routes.ingest_github(
            ingest_payload(),
            session=object(),
            settings=object(),
            embeddings=object(),
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "GitHub repository, branch, or path was not found."


@pytest.mark.asyncio
async def test_ingest_github_returns_bad_gateway_for_embedding_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ingest_github_repository(*args: object, **kwargs: object) -> None:
        raise EmbeddingProviderError(
            "Embedding provider returned an upstream error. Try again later."
        )

    monkeypatch.setattr(routes, "ingest_github_repository", fake_ingest_github_repository)

    with pytest.raises(HTTPException) as exc_info:
        await routes.ingest_github(
            ingest_payload(),
            session=object(),
            settings=object(),
            embeddings=object(),
        )

    assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY
    assert "Embedding provider returned an upstream error" in exc_info.value.detail


@pytest.mark.asyncio
async def test_ingest_github_returns_bad_gateway_for_invalid_github_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ingest_github_repository(*args: object, **kwargs: object) -> None:
        raise GithubClientError("GitHub returned an invalid contents response. Try again later.")

    monkeypatch.setattr(routes, "ingest_github_repository", fake_ingest_github_repository)

    with pytest.raises(HTTPException) as exc_info:
        await routes.ingest_github(
            ingest_payload(),
            session=object(),
            settings=object(),
            embeddings=object(),
        )

    assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY
    assert "GitHub returned an invalid contents response" in exc_info.value.detail
