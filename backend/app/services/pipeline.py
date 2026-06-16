from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.services.chunking import deduplicate_chunks, split_markdown
from app.services.embeddings import EmbeddingProvider
from app.services.github import GithubClient
from app.services.markdown import clean_markdown, extract_title
from app.services.repositories import upsert_document_with_chunks


@dataclass(frozen=True)
class IngestedDocumentResult:
    source_url: str
    title: str | None
    chunk_count: int


async def ingest_github_repository(
    session: AsyncSession,
    *,
    settings: Settings,
    embeddings: EmbeddingProvider,
    repo_url: str,
    branch: str | None,
    path: str,
    max_files: int,
) -> tuple[str, list[IngestedDocumentResult]]:
    github = GithubClient(settings)
    try:
        repo = await github.get_repo(repo_url)
        files = await github.fetch_markdown_files(
            repo,
            branch=branch,
            path=path,
            max_files=max_files,
        )
    finally:
        await github.close()

    results: list[IngestedDocumentResult] = []
    for file in files:
        cleaned = clean_markdown(file.content)
        if not cleaned:
            continue
        title = extract_title(cleaned, fallback=file.path.rsplit("/", maxsplit=1)[-1])
        chunks = deduplicate_chunks(split_markdown(cleaned, source_path=file.path))
        vectors = await embeddings.embed_texts([chunk.text for chunk in chunks])
        await upsert_document_with_chunks(
            session,
            source="github",
            source_url=file.html_url,
            title=title,
            content=cleaned,
            metadata={"repo": repo.full_name, "path": file.path, "sha": file.sha},
            chunks=chunks,
            embeddings=vectors,
        )
        results.append(
            IngestedDocumentResult(
                source_url=file.html_url,
                title=title,
                chunk_count=len(chunks),
            )
        )

    await session.commit()
    return repo.full_name, results
