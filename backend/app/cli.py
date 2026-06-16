import asyncio

import typer
from rich.console import Console

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.embeddings import build_embedding_provider
from app.services.pipeline import ingest_github_repository
from app.services.rag import build_extractive_answer
from app.services.repositories import retrieve_chunks

cli = typer.Typer(help="RAG Docs Pipeline command line tools.")
console = Console()


@cli.command()
def ingest_github(
    repo_url: str,
    branch: str | None = None,
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
def query(question: str, top_k: int = 5) -> None:
    """Run a semantic search query against the local vector database."""

    async def run() -> None:
        settings = get_settings()
        embeddings = build_embedding_provider(settings)
        query_embedding = await embeddings.embed_query(question)
        async with AsyncSessionLocal() as session:
            chunks = await retrieve_chunks(session, embedding=query_embedding, top_k=top_k)
        console.print(build_extractive_answer(question, chunks))

    asyncio.run(run())


if __name__ == "__main__":
    cli()
