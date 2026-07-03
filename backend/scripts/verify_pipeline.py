"""
verify_pipeline.py — Repeatable integration verification for the RAG pipeline.

Validates the full local loop:
  ingest (GitHub Markdown) -> persist (PostgreSQL/pgvector) -> retrieve -> query

Usage (from project root):
    cd backend
    PYTHONPATH=. python scripts/verify_pipeline.py

Requirements:
  - PostgreSQL with pgvector must be running and accessible via DATABASE_URL.
  - Alembic migrations must have been applied (alembic upgrade head).
  - backend/requirements.txt must be installed in the active Python environment.
  - .env or environment variables must configure DATABASE_URL.
  - No external paid API key is required when EMBEDDING_PROVIDER=local (default).
"""

import asyncio
import sys
import textwrap
from typing import Any

from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.models import DocSource, Document, DocumentChunk, QueryLog
from app.db.session import AsyncSessionLocal
from app.services.embeddings import build_embedding_provider
from app.services.pipeline import ingest_github_repository
from app.services.querying import run_query

console = Console()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VERIFY_REPO_URL = "https://github.com/tiangolo/fastapi"
VERIFY_MAX_FILES = 5
VERIFY_QUESTION = "How do I run FastAPI locally?"
VERIFY_SOURCE = "github"
VERIFY_MIN_CHUNKS = 1
VERIFY_MIN_DOCS = 1
VERIFY_MIN_SOURCES = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pass(label: str, detail: str = "") -> None:
    msg = f"[bold green]PASS[/bold green]  {label}"
    if detail:
        msg += f"  [dim]{detail}[/dim]"
    console.print(msg)


def _fail(label: str, detail: str = "") -> None:
    msg = f"[bold red]FAIL[/bold red]  {label}"
    if detail:
        msg += f"  [dim]{detail}[/dim]"
    console.print(msg)


def _info(label: str) -> None:
    console.print(f"[bold blue]INFO[/bold blue]  {label}")


# ---------------------------------------------------------------------------
# Verification steps
# ---------------------------------------------------------------------------


async def verify_database_connection() -> bool:
    """Confirm that the database is reachable and pgvector is available."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        _pass("Database connection")
    except Exception as exc:  # noqa: BLE001
        _fail("Database connection", str(exc))
        return False

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
        _pass("pgvector extension available")
    except Exception as exc:  # noqa: BLE001
        _fail("pgvector extension available", str(exc))
        return False

    return True


async def verify_tables_exist() -> bool:
    """Confirm all expected tables exist (migrations applied)."""
    expected = {"documents", "document_chunks", "doc_sources", "queries", "alembic_version"}
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            )
            found = {row[0] for row in result.fetchall()}
        missing = expected - found
        if missing:
            _fail("Expected tables exist", f"missing: {missing}")
            return False
        _pass("Expected tables exist", ", ".join(sorted(expected)))
        return True
    except Exception as exc:  # noqa: BLE001
        _fail("Expected tables exist", str(exc))
        return False


async def verify_ingest(settings: Any, embeddings: Any) -> tuple[bool, int, int]:
    """Ingest a small real GitHub repository and return (ok, doc_count, chunk_count)."""
    try:
        async with AsyncSessionLocal() as session:
            repository, documents = await ingest_github_repository(
                session,
                settings=settings,
                embeddings=embeddings,
                repo_url=VERIFY_REPO_URL,
                branch=None,
                path="",
                max_files=VERIFY_MAX_FILES,
            )
        doc_count = len(documents)
        chunk_count = sum(d.chunk_count for d in documents)
        if doc_count < VERIFY_MIN_DOCS:
            _fail(
                "Ingest documents",
                f"expected >= {VERIFY_MIN_DOCS}, got {doc_count}",
            )
            return False, doc_count, chunk_count
        if chunk_count < VERIFY_MIN_CHUNKS:
            _fail(
                "Ingest chunks",
                f"expected >= {VERIFY_MIN_CHUNKS}, got {chunk_count}",
            )
            return False, doc_count, chunk_count
        _pass(
            "Ingest documents and chunks",
            f"{doc_count} documents, {chunk_count} chunks from {repository}",
        )
        return True, doc_count, chunk_count
    except Exception as exc:  # noqa: BLE001
        _fail("Ingest documents and chunks", str(exc))
        return False, 0, 0


async def verify_persistence() -> tuple[bool, dict[str, int]]:
    """Confirm database counts match expected minimums after ingestion."""
    counts: dict[str, int] = {}
    try:
        async with AsyncSessionLocal() as session:
            counts["documents"] = (
                await session.execute(select(func.count()).select_from(Document))
            ).scalar_one()
            counts["document_chunks"] = (
                await session.execute(select(func.count()).select_from(DocumentChunk))
            ).scalar_one()
            counts["doc_sources"] = (
                await session.execute(select(func.count()).select_from(DocSource))
            ).scalar_one()
            counts["queries"] = (
                await session.execute(select(func.count()).select_from(QueryLog))
            ).scalar_one()

        checks = {
            "documents": VERIFY_MIN_DOCS,
            "document_chunks": VERIFY_MIN_CHUNKS,
            "doc_sources": VERIFY_MIN_SOURCES,
        }
        ok = True
        for table, minimum in checks.items():
            if counts[table] >= minimum:
                _pass(f"Persistence: {table}", f"count = {counts[table]}")
            else:
                _fail(f"Persistence: {table}", f"expected >= {minimum}, got {counts[table]}")
                ok = False

        # doc_sources must be linked: verify documents have doc_source_id set
        async with AsyncSessionLocal() as session:
            linked = (
                await session.execute(
                    select(func.count())
                    .select_from(Document)
                    .where(Document.doc_source_id.is_not(None))
                )
            ).scalar_one()
        if linked >= VERIFY_MIN_DOCS:
            _pass("Documents linked to doc_source", f"{linked} linked")
        else:
            _fail("Documents linked to doc_source", f"expected >= {VERIFY_MIN_DOCS}, got {linked}")
            ok = False

        return ok, counts
    except Exception as exc:  # noqa: BLE001
        _fail("Persistence checks", str(exc))
        return False, counts


async def verify_query(settings: Any, embeddings: Any) -> bool:
    """Run a query and confirm an answer and citations are returned."""
    try:
        async with AsyncSessionLocal() as session:
            result = await run_query(
                session,
                question=VERIFY_QUESTION,
                top_k=5,
                source=VERIFY_SOURCE,
                settings=settings,
                embeddings=embeddings,
            )

        has_answer = bool(result.answer.strip())
        has_chunks = result.retrieved_chunk_count > 0
        latency_ok = result.latency_ms >= 0
        query_id_ok = result.query_id > 0

        if has_answer:
            _pass("Query returns an answer", textwrap.shorten(result.answer, 80))
        else:
            _fail("Query returns an answer", "empty answer")

        if has_chunks:
            _pass(
                "Query retrieves chunks",
                f"{result.retrieved_chunk_count} chunks in {result.latency_ms}ms",
            )
        else:
            _fail("Query retrieves chunks", "0 chunks retrieved — check source filtering")

        if latency_ok:
            _pass("Query latency recorded", f"{result.latency_ms}ms")
        else:
            _fail("Query latency recorded", f"unexpected value: {result.latency_ms}")

        if query_id_ok:
            _pass("Query log persisted", f"query_id={result.query_id}")
        else:
            _fail("Query log persisted", f"unexpected query_id={result.query_id}")

        return has_answer and has_chunks and latency_ok and query_id_ok

    except Exception as exc:  # noqa: BLE001
        _fail("Query execution", str(exc))
        return False


async def verify_source_disable(settings: Any, embeddings: Any) -> bool:
    """Disable a source, confirm retrieval returns 0 chunks, then re-enable."""
    try:
        async with AsyncSessionLocal() as session:
            source = (
                await session.execute(
                    select(DocSource).where(DocSource.source_type == VERIFY_SOURCE).limit(1)
                )
            ).scalar_one_or_none()
            if source is None:
                _fail("Source disable: no source found to disable")
                return False
            source_id = source.id
            source.enabled = False
            await session.commit()

        async with AsyncSessionLocal() as session:
            result = await run_query(
                session,
                question=VERIFY_QUESTION,
                top_k=5,
                source=VERIFY_SOURCE,
                settings=settings,
                embeddings=embeddings,
            )
        chunks_when_disabled = result.retrieved_chunk_count

        # Re-enable immediately
        async with AsyncSessionLocal() as session:
            source = await session.get(DocSource, source_id)
            if source is not None:
                source.enabled = True
                await session.commit()

        if chunks_when_disabled == 0:
            _pass("Disabled source returns 0 chunks")
        else:
            _fail(
                "Disabled source returns 0 chunks",
                f"got {chunks_when_disabled} chunks — disable filter may be broken",
            )
            return False

        _pass("Source re-enabled after disable test")
        return True

    except Exception as exc:  # noqa: BLE001
        _fail("Source disable test", str(exc))
        return False


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------


def _print_summary(results: dict[str, bool]) -> bool:
    table = Table(title="Verification Summary", show_header=True, header_style="bold")
    table.add_column("Check", style="dim", width=40)
    table.add_column("Result", justify="center", width=10)
    all_pass = True
    for label, passed in results.items():
        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        table.add_row(label, status)
        if not passed:
            all_pass = False
    console.print()
    console.print(table)
    return all_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    console.rule("[bold]RAG Pipeline Verification[/bold]")
    settings = get_settings()
    embeddings = build_embedding_provider(settings)

    _info(f"Embedding provider: {settings.embedding_provider}")
    _info(f"Embedding dimensions: {settings.embedding_dimensions}")
    _info(f"Target repository: {VERIFY_REPO_URL} (max {VERIFY_MAX_FILES} files)")
    console.print()

    results: dict[str, bool] = {}

    # Step 1: database connectivity
    results["Database connection"] = await verify_database_connection()
    if not results["Database connection"]:
        console.print("[red]Cannot continue without a database. Aborting.[/red]")
        _print_summary(results)
        return 1

    # Step 2: tables
    results["Expected tables exist"] = await verify_tables_exist()
    if not results["Expected tables exist"]:
        console.print("[red]Missing tables. Run: cd backend && alembic upgrade head[/red]")
        _print_summary(results)
        return 1

    # Step 3: ingest
    console.print()
    _info(f"Ingesting {VERIFY_REPO_URL} (max_files={VERIFY_MAX_FILES}) …")
    ingest_ok, _docs, _chunks = await verify_ingest(settings, embeddings)
    results["Ingest documents and chunks"] = ingest_ok

    # Step 4: persistence
    console.print()
    _info("Checking persistence …")
    persist_ok, counts = await verify_persistence()
    results["Persistence counts"] = persist_ok

    # Step 5: query
    console.print()
    _info(f"Running query: {VERIFY_QUESTION!r} …")
    results["Query returns answer with citations"] = await verify_query(settings, embeddings)

    # Step 6: source disable
    console.print()
    _info("Testing source disable filter …")
    results["Disabled source excluded from retrieval"] = await verify_source_disable(
        settings, embeddings
    )

    # Summary
    all_pass = _print_summary(results)
    if all_pass:
        console.print("\n[bold green]All checks passed.[/bold green]")
        return 0
    else:
        console.print("\n[bold red]Some checks failed. Review output above.[/bold red]")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
