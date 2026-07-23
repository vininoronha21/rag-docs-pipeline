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
import re
import sys
import textwrap
from typing import Any

from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.models import DocSource, Document, DocumentChunk, QueryEvent, SourceVersion
from app.db.session import AsyncSessionLocal
from app.services.embeddings import build_embedding_provider
from app.services.pipeline import GithubIngestionResult, ingest_github_repository
from app.services.querying import run_query

console = Console()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VERIFY_REPO_URL = "https://github.com/fastapi/fastapi"
VERIFY_BRANCH = "master"
VERIFY_PATH = "docs/pt/docs"
VERIFY_MAX_FILES = 500
VERIFY_QUESTION = (
    "Como passo o path do arquivo `main.py` para `fastapi dev` ou a opção "
    "`--entrypoint main:app` para ele deduzir o objeto da aplicação?"
)
VERIFY_SOURCE = "github"
VERIFY_MIN_CHUNKS = 1
VERIFY_MIN_DOCS = 1
FORBIDDEN_QUERY_EVENT_FIELDS = {
    "question",
    "answer",
    "answer_text",
    "citation_snapshot",
    "citations",
    "retrieved_chunk_ids",
    "client_ip",
    "ip_address",
    "user_agent",
}


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
    expected = {
        "documents",
        "document_chunks",
        "doc_sources",
        "source_versions",
        "query_events",
        "alembic_version",
    }
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
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


async def verify_ingest(
    settings: Any,
    embeddings: Any,
) -> tuple[bool, GithubIngestionResult | None]:
    """Ingest a small repository snapshot and verify a repeated sync is a no-op."""
    try:
        async with AsyncSessionLocal() as session:
            result = await ingest_github_repository(
                session,
                settings=settings,
                embeddings=embeddings,
                repo_url=VERIFY_REPO_URL,
                branch=VERIFY_BRANCH,
                path=VERIFY_PATH,
                max_files=VERIFY_MAX_FILES,
            )
        persisted, counts = await verify_persistence(result)
        if not persisted:
            return False, None
        _pass(
            "Ingest documents and chunks",
            f"{counts['documents']} documents, {counts['document_chunks']} chunks "
            f"at commit {result.commit_sha}",
        )

        async with AsyncSessionLocal() as session:
            repeated = await ingest_github_repository(
                session,
                settings=settings,
                embeddings=embeddings,
                repo_url=VERIFY_REPO_URL,
                branch=VERIFY_BRANCH,
                path=VERIFY_PATH,
                max_files=VERIFY_MAX_FILES,
            )
        if (
            repeated.status != "no_op"
            or repeated.source_id != result.source_id
            or repeated.source_version_id != result.source_version_id
            or repeated.commit_sha != result.commit_sha
        ):
            _fail("Repeated synchronization is a no-op")
            return False, None
        repeated_persisted, repeated_counts = await verify_persistence(repeated)
        if not repeated_persisted or repeated_counts != counts:
            _fail("Repeated synchronization preserves target corpus counts")
            return False, None
        _pass(
            "Repeated synchronization is a no-op",
            f"source={repeated.source_id}, version={repeated.source_version_id}",
        )
        return True, repeated
    except Exception as exc:  # noqa: BLE001
        _fail("Ingest documents and chunks", str(exc))
        return False, None


async def verify_persistence(
    result: GithubIngestionResult,
) -> tuple[bool, dict[str, int]]:
    """Validate the source/version graph and real corpus counts for one ingestion result."""
    counts: dict[str, int] = {}
    try:
        async with AsyncSessionLocal() as session:
            source = await session.get(DocSource, result.source_id)
            version = await session.get(SourceVersion, result.source_version_id)
            documents = list(
                (
                    await session.scalars(
                        select(Document).where(
                            Document.source_version_id == result.source_version_id
                        )
                    )
                ).all()
            )
            chunk_count = await session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(Document.source_version_id == result.source_version_id)
            )

        counts = {
            "documents": len(documents),
            "document_chunks": chunk_count or 0,
        }
        checks = [
            (source is not None, "Target source exists"),
            (version is not None, "Target source version exists"),
        ]
        if source is not None:
            checks.extend(
                [
                    (source.repository == result.repository, "Source repository matches result"),
                    (source.branch == result.branch, "Source branch matches result"),
                    (source.path == result.path, "Source path matches result"),
                    (source.enabled is True, "Target source is enabled"),
                    (
                        source.active_version_id == result.source_version_id,
                        "Result version is active for source",
                    ),
                ]
            )
        if version is not None:
            checks.extend(
                [
                    (version.source_id == result.source_id, "Version belongs to result source"),
                    (version.commit_sha == result.commit_sha, "Version commit matches result"),
                    (
                        version.document_count == counts["documents"],
                        "Stored document count matches real documents",
                    ),
                    (
                        version.chunk_count == counts["document_chunks"],
                        "Stored chunk count matches real chunks",
                    ),
                ]
            )
        checks.extend(
            [
                (
                    all(
                        document.source_version_id == result.source_version_id
                        for document in documents
                    ),
                    "Every document belongs to result version",
                ),
                (counts["documents"] >= VERIFY_MIN_DOCS, "Target version has documents"),
                (counts["document_chunks"] >= VERIFY_MIN_CHUNKS, "Target version has chunks"),
            ]
        )
        if result.status == "synchronized":
            checks.extend(
                [
                    (
                        len(result.documents) == counts["documents"],
                        "Result document count matches persistence",
                    ),
                    (
                        sum(document.chunk_count for document in result.documents)
                        == counts["document_chunks"],
                        "Result chunk count matches persistence",
                    ),
                ]
            )

        ok = True
        for passed, label in checks:
            if passed:
                _pass(label)
            else:
                _fail(label)
                ok = False
        return ok, counts
    except Exception as exc:  # noqa: BLE001
        _fail("Persistence checks", str(exc))
        return False, counts


async def verify_query(
    settings: Any,
    embeddings: Any,
    target: GithubIngestionResult,
) -> bool:
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
                source_id=target.source_id,
            )
            event = await session.get(QueryEvent, result.event_id) if result.event_id else None

        answer_text = (
            " ".join(sentence.text for sentence in result.answer.sentences)
            if result.answer is not None
            else ""
        )
        state = getattr(result, "state", "answered" if answer_text.strip() else None)
        has_answer = bool(answer_text.strip())
        has_chunks = result.metrics.retrieved_chunk_count > 0
        latency_ok = result.metrics.latency_ms >= 0
        event_id_ok = bool(result.event_id)
        state_ok = state == "answered"
        citations_ok = _verify_answer_citations(result, target) if has_answer else False
        event_schema_ok = _verify_anonymous_query_event(
            event,
            result=result,
            target=target,
            state=state,
        )

        if has_answer:
            _pass("Query returns an answer", textwrap.shorten(answer_text, 80))
        else:
            _fail("Query returns an answer", "empty answer")

        if has_chunks:
            _pass(
                "Query retrieves chunks",
                f"{result.metrics.retrieved_chunk_count} chunks in {result.metrics.latency_ms}ms",
            )
        else:
            _fail("Query retrieves chunks", "0 chunks retrieved — check source filtering")

        if latency_ok:
            _pass("Query latency recorded", f"{result.metrics.latency_ms}ms")
        else:
            _fail("Query latency recorded", f"unexpected value: {result.metrics.latency_ms}")

        if state_ok:
            _pass("Query state is answered")
        else:
            _fail("Query state is answered", f"state={state!r}")

        if event_id_ok:
            _pass("Anonymous query event persisted", f"event_id={result.event_id}")
        else:
            _fail("Anonymous query event persisted", f"unexpected event_id={result.event_id}")

        return (
            has_answer
            and has_chunks
            and latency_ok
            and event_id_ok
            and state_ok
            and citations_ok
            and event_schema_ok
        )

    except Exception as exc:  # noqa: BLE001
        _fail("Query execution", str(exc))
        return False


def _verify_answer_citations(result: Any, target: GithubIngestionResult) -> bool:
    evidence = list(getattr(result, "evidence", []) or [])
    evidence_by_citation_id = {
        citation_id.strip(): item
        for item in evidence
        if isinstance(citation_id := getattr(item, "citation_id", None), str)
        and citation_id.strip()
    }
    evidence_by_chunk_id = {
        chunk_id: item
        for item in evidence
        if isinstance(chunk_id := getattr(item, "chunk_id", None), int)
        and not isinstance(chunk_id, bool)
    }
    if not evidence_by_citation_id:
        _fail("Answered citations include cited evidence", "no citation_id found")
        return False

    ok = True
    answer = getattr(result, "answer", None)
    sentences = list(getattr(answer, "sentences", []) or [])
    sentence_citation_ids: list[str] = []
    for index, sentence in enumerate(sentences, start=1):
        if hasattr(sentence, "citation_id"):
            citation_id = getattr(sentence, "citation_id", None)
        else:
            chunk_id = getattr(sentence, "chunk_id", None)
            chunk_evidence = evidence_by_chunk_id.get(chunk_id)
            citation_id = getattr(chunk_evidence, "citation_id", None) if chunk_evidence else None

        if not isinstance(citation_id, str) or not citation_id.strip():
            _fail("Answer sentence includes citation ID", f"sentence {index}")
            ok = False
            continue

        citation_id = citation_id.strip()
        if citation_id not in evidence_by_citation_id:
            _fail("Answer sentence citation maps to evidence", citation_id)
            ok = False
            continue
        sentence_citation_ids.append(citation_id)

    if not sentence_citation_ids:
        return False

    for citation_id in dict.fromkeys(sentence_citation_ids):
        item = evidence_by_citation_id[citation_id]
        supported_text = getattr(item, "supported_text", None)
        repository_path = getattr(item, "repository_path", "")
        commit_sha = getattr(item, "commit_sha", "")
        source_url = getattr(item, "source_url", "")
        chunk_id = getattr(item, "chunk_id", None)
        path_prefix = target.path.rstrip("/")

        if not isinstance(supported_text, str) or not supported_text.strip():
            _fail("Answered citations include supported text", getattr(item, "citation_id", ""))
            ok = False

        if not isinstance(chunk_id, int) or isinstance(chunk_id, bool):
            _fail("Answered citations include chunk metadata", getattr(item, "citation_id", ""))
            ok = False

        if not isinstance(repository_path, str) or not (
            repository_path == path_prefix or repository_path.startswith(f"{path_prefix}/")
        ):
            _fail("Answered citations stay inside target source path", str(repository_path))
            ok = False

        if not isinstance(commit_sha, str) or re.fullmatch(r"[0-9a-f]{40}", commit_sha) is None:
            _fail("Answered citations include 40-hex commit SHA", str(commit_sha))
            ok = False
        elif commit_sha != target.commit_sha:
            _fail("Answered citations use target source version", commit_sha)
            ok = False

        expected_prefix = f"https://github.com/{target.repository}/blob/{commit_sha}/"
        if not isinstance(source_url, str) or not source_url.startswith(expected_prefix):
            _fail("Answered citations use commit-pinned GitHub URLs", str(source_url))
            ok = False

    if ok:
        _pass(
            "Answer sentences cite commit-pinned evidence",
            f"{len(sentences)} sentences, {len(set(sentence_citation_ids))} citations",
        )
    return ok


def _verify_anonymous_query_event(
    event: Any,
    *,
    result: Any,
    target: GithubIngestionResult,
    state: str | None,
) -> bool:
    if event is None:
        _fail("Anonymous query event schema", "event row not found")
        return False

    event_fields = set(getattr(event, "__dict__", {}).keys()) - {"_sa_instance_state"}
    forbidden_fields = sorted(event_fields & FORBIDDEN_QUERY_EVENT_FIELDS)
    if forbidden_fields:
        _fail("Anonymous query event stores no visitor content", ", ".join(forbidden_fields))
        return False

    checks = [
        (getattr(event, "id", None) == result.event_id, "Event id matches query result"),
        (getattr(event, "state", None) == state, "Event state matches query result"),
        (
            getattr(event, "latency_ms", None) == result.metrics.latency_ms,
            "Event latency matches query metrics",
        ),
        (
            getattr(event, "retrieved_chunk_count", None)
            == result.metrics.retrieved_chunk_count,
            "Event result count matches query metrics",
        ),
        (
            sorted(getattr(event, "source_ids", []) or []) == [target.source_id],
            "Event source id is target-only",
        ),
        (
            sorted(getattr(event, "source_version_ids", []) or [])
            == [target.source_version_id],
            "Event source version id is target-only",
        ),
        (
            getattr(event, "top_fused_score", None) == result.metrics.top_fused_score,
            "Event top score matches query metrics",
        ),
        (
            getattr(event, "score_gap", None) == result.metrics.score_gap,
            "Event score gap matches query metrics",
        ),
        (getattr(event, "feedback", None) is None, "Event feedback starts empty"),
    ]

    ok = True
    for passed, label in checks:
        if passed:
            _pass(label)
        else:
            _fail(label)
            ok = False
    if ok:
        _pass("Anonymous query event stores no visitor content")
    return ok


async def verify_source_disable(
    settings: Any,
    embeddings: Any,
    result: GithubIngestionResult,
) -> bool:
    """Disable the verification source, test retrieval, then restore its prior state."""
    source_id: int | None = None
    previous_enabled: bool | None = None
    try:
        async with AsyncSessionLocal() as session:
            source = await session.get(DocSource, result.source_id)
            if (
                source is None
                or source.repository != result.repository
                or source.branch != result.branch
                or source.path != result.path
                or source.active_version_id != result.source_version_id
            ):
                _fail("Source disable: ingestion target is no longer active")
                return False
            source_id = result.source_id
            previous_enabled = source.enabled
            source.enabled = False
            await session.commit()

        try:
            async with AsyncSessionLocal() as session:
                result = await run_query(
                    session,
                    question=VERIFY_QUESTION,
                    top_k=5,
                    source=VERIFY_SOURCE,
                    settings=settings,
                    embeddings=embeddings,
                    source_id=source_id,
                )
            chunks_when_disabled = result.metrics.retrieved_chunk_count
        finally:
            async with AsyncSessionLocal() as session:
                source = await session.get(DocSource, source_id)
                if source is not None:
                    source.enabled = previous_enabled
                    await session.commit()

        if chunks_when_disabled == 0:
            _pass("Disabled source returns 0 chunks")
        else:
            _fail(
                "Disabled source returns 0 chunks",
                f"got {chunks_when_disabled} chunks — disable filter may be broken",
            )
            return False

        _pass("Source state restored after disable test")
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
    ingest_ok, target = await verify_ingest(settings, embeddings)
    results["Ingest documents and chunks"] = ingest_ok

    # Step 4: persistence
    console.print()
    _info("Checking persistence …")
    persist_ok = False
    if target is not None:
        persist_ok, _counts = await verify_persistence(target)
    results["Persistence counts"] = persist_ok

    # Step 5: query
    console.print()
    _info(f"Running query: {VERIFY_QUESTION!r} …")
    results["Query returns answer with citations"] = (
        await verify_query(settings, embeddings, target) if target is not None else False
    )

    # Step 6: source disable
    console.print()
    _info("Testing source disable filter …")
    results["Disabled source excluded from retrieval"] = (
        await verify_source_disable(settings, embeddings, target) if target is not None else False
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
