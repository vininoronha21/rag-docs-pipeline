import asyncio
from typing import Optional

import typer
from rich.console import Console

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.embeddings import build_embedding_provider
from app.services.pipeline import ingest_github_repository
from app.services.querying import run_query

cli = typer.Typer(help="RAG Docs Pipeline command line tools.")
console = Console()


@cli.command()
def ingest_github(
    repo_url: str,
    branch: Optional[str] = None,  # noqa: UP007 - Typer 0.12 needs typing.Optional.
    path: str = "",
    max_files: int = 50,
) -> None:
    """Ingest Markdown documentation from a GitHub repository."""

    async def run() -> None:
        settings = get_settings()
        embeddings = build_embedding_provider(settings)
        async with AsyncSessionLocal() as session:
            repository, documents = await ingest_github_repository(
                session,
                settings=settings,
                embeddings=embeddings,
                repo_url=repo_url,
                branch=branch,
                path=path,
                max_files=max_files,
            )
        console.print(f"Ingested {len(documents)} documents from {repository}")
        console.print(f"Total chunks: {sum(document.chunk_count for document in documents)}")

    asyncio.run(run())


@cli.command()
def query(
    question: str,
    top_k: int = 5,
    source: Optional[str] = None,  # noqa: UP007 - Typer 0.12 needs typing.Optional.
) -> None:
    """Run a semantic search query against the local vector database."""

    answer, query_id, retrieved_chunk_count, latency_ms = asyncio.run(
        _run_query(question, top_k=top_k, source=source)
    )
    console.print(answer)
    console.print(f"Query {query_id}: {retrieved_chunk_count} chunks in {latency_ms}ms")


async def _run_query(
    question: str,
    *,
    top_k: int,
    source: str | None,
) -> tuple[str, int, int, int]:
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
    return result.answer, result.query_id, result.retrieved_chunk_count, result.latency_ms


if __name__ == "__main__":
    cli()
