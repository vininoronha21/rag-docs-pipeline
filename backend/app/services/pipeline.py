from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.services.chunking import deduplicate_chunks, split_markdown
from app.services.embeddings import EmbeddingProvider
from app.services.github import GithubClient, normalize_repository_path
from app.services.markdown import clean_markdown, extract_title
from app.services.repositories import (
    SourceVersionDocument,
    create_source_version_with_documents,
    get_active_source_version,
    get_or_create_doc_source,
    promote_source_version,
)


@dataclass(frozen=True)
class IngestedDocumentResult:
    source_url: str
    title: str | None
    chunk_count: int


@dataclass(frozen=True)
class GithubIngestionResult:
    status: Literal["synchronized", "no_op"]
    repository: str
    branch: str
    path: str
    commit_sha: str
    source_id: int
    source_version_id: int
    documents: list[IngestedDocumentResult]


async def ingest_github_repository(
    session: AsyncSession,
    *,
    settings: Settings,
    embeddings: EmbeddingProvider,
    repo_url: str,
    branch: str | None,
    path: str,
    max_files: int,
) -> GithubIngestionResult:
    github = GithubClient(settings)
    try:
        try:
            repo = await github.get_repo(repo_url)
            effective_branch = branch or repo.default_branch
            normalized_path = normalize_repository_path(path)
            commit_sha = await github.resolve_commit(repo, branch=effective_branch)
            source = await get_or_create_doc_source(
                session,
                repository=repo.full_name,
                branch=effective_branch,
                path=normalized_path,
            )
            active_version = await get_active_source_version(session, source=source)
            if active_version is not None and active_version.commit_sha == commit_sha:
                return GithubIngestionResult(
                    status="no_op",
                    repository=repo.full_name,
                    branch=effective_branch,
                    path=normalized_path,
                    commit_sha=commit_sha,
                    source_id=source.id,
                    source_version_id=active_version.id,
                    documents=[],
                )

            files = await github.fetch_markdown_files(
                repo,
                commit_sha=commit_sha,
                path=normalized_path,
                max_files=max_files,
            )
            candidate_documents: list[SourceVersionDocument] = []
            results: list[IngestedDocumentResult] = []
            for file in files:
                cleaned = clean_markdown(file.content)
                if not cleaned:
                    continue
                title = extract_title(cleaned, fallback=file.path.rsplit("/", maxsplit=1)[-1])
                chunks = deduplicate_chunks(split_markdown(cleaned, source_path=file.path))
                vectors = await embeddings.embed_texts([chunk.text for chunk in chunks])
                candidate_documents.append(
                    SourceVersionDocument(
                        repository_path=file.path,
                        source="github",
                        source_url=file.html_url,
                        title=title,
                        content=cleaned,
                        metadata={
                            "repo": repo.full_name,
                            "path": file.path,
                            "sha": file.sha,
                            "commit_sha": commit_sha,
                        },
                        chunks=chunks,
                        embeddings=vectors,
                    )
                )
                results.append(
                    IngestedDocumentResult(
                        source_url=file.html_url,
                        title=title,
                        chunk_count=len(chunks),
                    )
                )

            version = await create_source_version_with_documents(
                session,
                source=source,
                commit_sha=commit_sha,
                embedding_provider=settings.embedding_provider,
                embedding_model=_embedding_model(settings),
                embedding_dimensions=embeddings.dimensions,
                documents=candidate_documents,
            )
            await promote_source_version(session, source=source, version=version, retention=5)
            result = GithubIngestionResult(
                status="synchronized",
                repository=repo.full_name,
                branch=effective_branch,
                path=normalized_path,
                commit_sha=commit_sha,
                source_id=source.id,
                source_version_id=version.id,
                documents=results,
            )
        finally:
            await github.close()

        await session.commit()
        return result
    except Exception:
        await session.rollback()
        raise


def _embedding_model(settings: Settings) -> str:
    if settings.embedding_provider == "openai":
        return settings.openai_embedding_model
    return "hash"
