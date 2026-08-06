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
    get_doc_source_by_identity,
    get_doc_source_for_update,
    get_or_create_doc_source,
    get_source_version_by_commit,
    promote_source_version,
)


class SourceSynchronizationConflict(RuntimeError):
    """Raised when another synchronization promotes a different commit first."""


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
        repo = await github.get_repo(repo_url)
        effective_branch = branch or repo.default_branch
        normalized_path = normalize_repository_path(path)
        commit_sha = await github.resolve_commit(repo, branch=effective_branch)

        try:
            observed_source = await get_doc_source_by_identity(
                session,
                repository=repo.full_name,
                branch=effective_branch,
                path=normalized_path,
            )
            observed_active = (
                await get_active_source_version(session, source=observed_source)
                if observed_source is not None
                else None
            )
            observed_active_version_id = (
                observed_source.active_version_id if observed_source is not None else None
            )
            observed_source_id = observed_source.id if observed_source is not None else None
            observed_active_id = observed_active.id if observed_active is not None else None
            observed_active_commit = (
                observed_active.commit_sha if observed_active is not None else None
            )
        except Exception:
            await session.rollback()
            raise
        await session.rollback()

        if (
            observed_source_id is not None
            and observed_active_id is not None
            and observed_active_commit == commit_sha
        ):
            return _ingestion_result(
                status="no_op",
                repository=repo.full_name,
                branch=effective_branch,
                path=normalized_path,
                commit_sha=commit_sha,
                source_id=observed_source_id,
                source_version_id=observed_active_id,
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
        if not candidate_documents:
            raise ValueError(
                "No indexable Markdown content was found in the selected repository path."
            )
    finally:
        await github.close()

    try:
        source = await get_or_create_doc_source(
            session,
            repository=repo.full_name,
            branch=effective_branch,
            path=normalized_path,
        )
        source_id = source.id
        locked_source = await get_doc_source_for_update(session, source_id=source_id)
        if locked_source is None:
            raise RuntimeError("Document source no longer exists.")
        locked_active = await get_active_source_version(session, source=locked_source)
        if locked_active is not None and locked_active.commit_sha == commit_sha:
            locked_active_id = locked_active.id
            await session.rollback()
            return _ingestion_result(
                status="no_op",
                repository=repo.full_name,
                branch=effective_branch,
                path=normalized_path,
                commit_sha=commit_sha,
                source_id=source_id,
                source_version_id=locked_active_id,
                documents=[],
            )
        if locked_source.active_version_id != observed_active_version_id:
            raise SourceSynchronizationConflict(
                "Source changed while synchronization was being prepared. Retry synchronization."
            )

        version = await get_source_version_by_commit(
            session,
            source_id=source_id,
            commit_sha=commit_sha,
        )
        if version is None:
            version = await create_source_version_with_documents(
                session,
                source=locked_source,
                commit_sha=commit_sha,
                embedding_provider=settings.embedding_provider,
                embedding_model=_embedding_model(settings),
                embedding_dimensions=embeddings.dimensions,
                documents=candidate_documents,
            )
        await promote_source_version(session, source=locked_source, version=version, retention=5)
        version_id = version.id
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return _ingestion_result(
        status="synchronized",
        repository=repo.full_name,
        branch=effective_branch,
        path=normalized_path,
        commit_sha=commit_sha,
        source_id=source_id,
        source_version_id=version_id,
        documents=results,
    )


def _ingestion_result(
    *,
    status: Literal["synchronized", "no_op"],
    repository: str,
    branch: str,
    path: str,
    commit_sha: str,
    source_id: int,
    source_version_id: int,
    documents: list[IngestedDocumentResult],
) -> GithubIngestionResult:
    return GithubIngestionResult(
        status=status,
        repository=repository,
        branch=branch,
        path=path,
        commit_sha=commit_sha,
        source_id=source_id,
        source_version_id=source_version_id,
        documents=documents,
    )


def _embedding_model(settings: Settings) -> str:
    if settings.embedding_provider == "openai":
        return settings.openai_embedding_model
    return "hash"
