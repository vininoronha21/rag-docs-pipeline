import asyncio
import time
from typing import Optional

import typer
from rich.console import Console

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.embeddings import build_embedding_provider
from app.services.pipeline import ingest_github_repository
from app.services.rag import (
    build_extractive_answer,
    filter_chunks_by_min_score,
    filter_prompt_injection_chunks,
)
from app.services.repositories import log_query, retrieve_chunks

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
    started_at = time.perf_counter()
    query_embedding = await embeddings.embed_query(question)
    async with AsyncSessionLocal() as session:
        chunks = await retrieve_chunks(
            session,
            embedding=query_embedding,
            top_k=top_k,
            source=source,
        )
        chunks = filter_chunks_by_min_score(chunks, min_score=settings.retrieval_min_score)
        chunks = filter_prompt_injection_chunks(chunks)
        answer = build_extractive_answer(question, chunks)
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        query_log = await log_query(
            session,
            question=question,
            retrieved_chunk_ids=[chunk.id for chunk in chunks],
            answer=answer,
            latency_ms=latency_ms,
            retrieved_chunk_count=len(chunks),
        )
        await session.commit()
    return answer, query_log.id, query_log.retrieved_chunk_count, query_log.latency_ms


if __name__ == "__main__":
    cli()
