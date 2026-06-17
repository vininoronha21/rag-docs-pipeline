from types import SimpleNamespace

import pytest

from app.services import pipeline


class FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


class FakeEmbeddings:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _text in texts]


class FakeGithubClient:
    def __init__(self, settings: object) -> None:
        assert settings is not None

    async def get_repo(self, repo_url: str) -> SimpleNamespace:
        assert repo_url == "https://github.com/example/project"
        return SimpleNamespace(full_name="example/project", default_branch="main")

    async def fetch_markdown_files(
        self,
        repo: SimpleNamespace,
        *,
        branch: str | None,
        path: str,
        max_files: int,
    ) -> list[SimpleNamespace]:
        assert repo.full_name == "example/project"
        assert branch is None
        assert path == "docs"
        assert max_files == 1
        return [
            SimpleNamespace(
                path="docs/index.md",
                html_url="https://github.com/example/project/blob/main/docs/index.md",
                sha="abc123",
                content="# Install\n\nRun the server.",
            )
        ]

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_ingest_github_repository_links_documents_to_doc_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_document_kwargs: dict[str, object] = {}

    async def fake_upsert_doc_source(*args: object, **kwargs: object) -> SimpleNamespace:
        assert args == (session,)
        assert kwargs["source_type"] == "github"
        assert kwargs["source_config"] == {
            "repo": "example/project",
            "branch": "main",
            "path": "docs",
        }
        return SimpleNamespace(id=9)

    async def fake_upsert_document_with_chunks(*args: object, **kwargs: object) -> None:
        assert args == (session,)
        captured_document_kwargs.update(kwargs)

    monkeypatch.setattr(pipeline, "GithubClient", FakeGithubClient)
    monkeypatch.setattr(pipeline, "upsert_doc_source", fake_upsert_doc_source)
    monkeypatch.setattr(pipeline, "upsert_document_with_chunks", fake_upsert_document_with_chunks)
    session = FakeSession()

    repository, documents = await pipeline.ingest_github_repository(
        session,
        settings=object(),
        embeddings=FakeEmbeddings(),
        repo_url="https://github.com/example/project",
        branch=None,
        path="docs",
        max_files=1,
    )

    assert repository == "example/project"
    assert len(documents) == 1
    assert captured_document_kwargs["doc_source_id"] == 9
    assert session.committed is True
