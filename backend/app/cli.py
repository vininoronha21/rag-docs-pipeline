import asyncio
from typing import Optional

import typer
from rich.console import Console

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.embeddings import build_embedding_provider
from app.services.pipeline import ingest_github_repository
from app.services.querying import QueryExecutionResult, run_query

cli = typer.Typer(help="RAG Docs Pipeline command line tools.")
console = Console()


@cli.command()
def ingest_github(
    repo_url: str,
    path: str,
    branch: Optional[str] = None,  # noqa: UP007 - Typer 0.12 needs typing.Optional.
    max_files: int = 50,
) -> None:
    """Ingest Markdown documentation from a GitHub repository."""
    if not path:
        raise typer.BadParameter("Path must not be empty.", param_hint="path")
    if max_files < 1 or max_files > 500:
        raise typer.BadParameter(
            "Must be between 1 and 500.",
            param_hint="max-files",
        )

    async def run() -> None:
        settings = get_settings()
        embeddings = build_embedding_provider(settings)
        async with AsyncSessionLocal() as session:
            result = await ingest_github_repository(
                session,
                settings=settings,
                embeddings=embeddings,
                repo_url=repo_url,
                branch=branch,
                path=path,
                max_files=max_files,
            )
        if result.status == "no_op":
            console.print(f"No changes: {result.repository} is already synchronized")
        else:
            console.print(
                f"Synchronized {len(result.documents)} documents from {result.repository}"
            )
        console.print(f"Branch: {result.branch}")
        console.print(f"Path: {result.path}")
        console.print(f"Commit: {result.commit_sha}")
        console.print(f"Source ID: {result.source_id}")
        console.print(f"Version: {result.source_version_id}")
        if result.documents:
            console.print("Documents:")
            for document in result.documents:
                title = document.title or "(untitled)"
                console.print(
                    f"- {document.source_url} | {title} | {document.chunk_count} chunks"
                )
        else:
            console.print("Documents: none")
        console.print(f"Total chunks: {sum(document.chunk_count for document in result.documents)}")

    asyncio.run(run())


@cli.command()
def query(
    question: str,
    top_k: int = typer.Option(5, min=1, max=12),
    source: Optional[str] = None,  # noqa: UP007 - Typer 0.12 needs typing.Optional.
) -> None:
    """Run a semantic search query against the local vector database."""

    try:
        result = asyncio.run(_run_query(question, top_k=top_k, source=source))
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if result.answer is None:
        console.print("Insufficient evidence to answer. Best retrieved excerpts:")
    else:
        citation_ids = {
            item.chunk_id: item.citation_id
            for item in result.evidence
            if item.citation_id is not None
        }
        for sentence in result.answer.sentences:
            citation = citation_ids.get(sentence.chunk_id)
            suffix = f" [{citation}]" if citation else ""
            console.print(f"{sentence.text}{suffix}")
    for item in result.evidence:
        console.print(f"- {item.title or item.repository_path}: {item.source_url}")
    console.print(
        f"Event {result.event_id} ({result.state}): "
        f"{result.metrics.retrieved_chunk_count} chunks in {result.metrics.latency_ms}ms"
    )


async def _run_query(
    question: str,
    *,
    top_k: int,
    source: str | None,
) -> QueryExecutionResult:
    settings = get_settings()
    embeddings = build_embedding_provider(settings)
    async with AsyncSessionLocal() as session:
        result = await run_query(
            session,
            question=question,
            top_k=top_k,
            source=source,
            settings=settings,
            embeddings=embeddings,
        )
    return result


if __name__ == "__main__":
    cli()
