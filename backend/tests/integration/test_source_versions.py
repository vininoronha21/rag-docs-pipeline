import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import Connection, delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.db.models import DocSource, Document, SourceVersion
from app.services import pipeline
from app.services.chunking import Chunk
from app.services.repositories import (
    SourceVersionDocument,
    create_source_version_with_documents,
    get_analytics_summary,
    get_doc_source_for_update,
    get_or_create_doc_source,
    promote_source_version,
    retrieve_chunks,
)


class AsyncSessionFacade:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, item: object) -> None:
        self.session.add(item)

    async def flush(self) -> None:
        self.session.flush()

    async def scalar(self, statement: object) -> object:
        return self.session.scalar(statement)

    async def execute(self, statement: object, params: dict[str, object] | None = None) -> object:
        return self.session.execute(statement, params or {})


def _insert_source(connection: Connection, *, repository: str = "example/project") -> int:
    return connection.execute(
        text(
            "INSERT INTO doc_sources "
            "(source_type, source_config, enabled, repository, branch, path, language) "
            "VALUES ('github', '{}', true, :repository, 'main', 'docs', 'pt-BR') "
            "RETURNING id"
        ),
        {"repository": repository},
    ).scalar_one()


def _insert_version(
    connection: Connection,
    source_id: int,
    *,
    commit_sha: str = "a" * 40,
) -> int:
    return connection.execute(
        text(
            "INSERT INTO source_versions "
            "(source_id, commit_sha, embedding_provider, embedding_model, "
            "embedding_dimensions, document_count, chunk_count) "
            "VALUES (:source_id, :commit_sha, 'local', 'hash', 1536, 1, 1) "
            "RETURNING id"
        ),
        {"source_id": source_id, "commit_sha": commit_sha},
    ).scalar_one()


def _insert_document_with_chunk(
    connection: Connection,
    *,
    version_id: int,
    repository_path: str,
    chunk_hash: str,
) -> None:
    document_id = connection.execute(
        text(
            "INSERT INTO documents "
            "(source_version_id, repository_path, source, source_url, content) "
            "VALUES (:version_id, :path, 'github', 'https://example.test/doc', 'content') "
            "RETURNING id"
        ),
        {"version_id": version_id, "path": repository_path},
    ).scalar_one()
    connection.execute(
        text(
            "INSERT INTO document_chunks "
            "(document_id, chunk_text, chunk_index, chunk_hash, embedding, chunk_metadata) "
            "VALUES (:document_id, 'content', 0, :chunk_hash, CAST(:embedding AS vector), '{}')"
        ),
        {
            "document_id": document_id,
            "chunk_hash": chunk_hash,
            "embedding": "[" + ",".join(["0"] * 1536) + "]",
        },
    )


def test_orm_metadata_matches_source_version_ownership() -> None:
    assert set(SourceVersion.__table__.columns.keys()) >= {
        "source_id",
        "commit_sha",
        "synced_at",
        "embedding_provider",
        "embedding_model",
        "embedding_dimensions",
        "document_count",
        "chunk_count",
    }
    assert next(iter(SourceVersion.source_id.foreign_keys)).ondelete == "CASCADE"
    active_version_fk = next(iter(DocSource.active_version_id.foreign_keys))
    assert active_version_fk.ondelete == "SET NULL"
    assert active_version_fk.use_alter is True
    assert next(iter(Document.source_version_id.foreign_keys)).ondelete == "CASCADE"
    assert "doc_source_id" not in Document.__table__.columns
    assert not hasattr(Document, "doc_source_id")
    assert not hasattr(Document, "doc_source")
    assert not hasattr(DocSource, "documents")
    assert SourceVersion.source.property.back_populates == "versions"
    assert SourceVersion.documents.property.back_populates == "source_version"


@pytest.mark.integration
def test_source_version_schema_constraints(sync_connection: Connection) -> None:
    constraints = dict(
        sync_connection.execute(
            text(
                "SELECT conname, pg_get_constraintdef(oid) "
                "FROM pg_constraint "
                "WHERE conname = ANY(:names)"
            ),
            {
                "names": [
                    "uq_doc_sources_repository_branch_path",
                    "uq_source_versions_source_commit",
                    "ck_source_versions_embedding_dimensions_positive",
                    "ck_source_versions_document_count_nonnegative",
                    "ck_source_versions_chunk_count_nonnegative",
                    "uq_documents_version_path",
                ]
            },
        ).all()
    )

    assert constraints == {
        "uq_doc_sources_repository_branch_path": "UNIQUE (repository, branch, path)",
        "uq_source_versions_source_commit": "UNIQUE (source_id, commit_sha)",
        "ck_source_versions_embedding_dimensions_positive": "CHECK ((embedding_dimensions > 0))",
        "ck_source_versions_document_count_nonnegative": "CHECK ((document_count >= 0))",
        "ck_source_versions_chunk_count_nonnegative": "CHECK ((chunk_count >= 0))",
        "uq_documents_version_path": "UNIQUE (source_version_id, repository_path)",
    }
    sync_connection.rollback()


@pytest.mark.integration
def test_analytics_summary_reports_enabled_active_corpus_counts(
    sync_connection: Connection,
) -> None:
    transaction = sync_connection.begin_nested()
    try:
        enabled_source_id = _insert_source(sync_connection, repository="enabled/project")
        enabled_active_version_id = _insert_version(sync_connection, enabled_source_id)
        enabled_retained_version_id = _insert_version(
            sync_connection,
            enabled_source_id,
            commit_sha="b" * 40,
        )
        disabled_source_id = _insert_source(sync_connection, repository="disabled/project")
        disabled_active_version_id = _insert_version(
            sync_connection,
            disabled_source_id,
            commit_sha="c" * 40,
        )
        sync_connection.execute(
            text("UPDATE doc_sources SET active_version_id = :version_id WHERE id = :source_id"),
            {"version_id": enabled_active_version_id, "source_id": enabled_source_id},
        )
        sync_connection.execute(
            text(
                "UPDATE doc_sources SET active_version_id = :version_id, enabled = false "
                "WHERE id = :source_id"
            ),
            {"version_id": disabled_active_version_id, "source_id": disabled_source_id},
        )
        _insert_document_with_chunk(
            sync_connection,
            version_id=enabled_active_version_id,
            repository_path="docs/enabled-active.md",
            chunk_hash="a" * 64,
        )
        _insert_document_with_chunk(
            sync_connection,
            version_id=enabled_retained_version_id,
            repository_path="docs/enabled-retained.md",
            chunk_hash="b" * 64,
        )
        _insert_document_with_chunk(
            sync_connection,
            version_id=disabled_active_version_id,
            repository_path="docs/disabled-active.md",
            chunk_hash="c" * 64,
        )

        with Session(bind=sync_connection, expire_on_commit=False) as session:
            summary = asyncio.run(get_analytics_summary(AsyncSessionFacade(session)))

        assert summary.document_count == 3
        assert summary.chunk_count == 3
        assert summary.active_document_count == 1
        assert summary.active_chunk_count == 1
    finally:
        transaction.rollback()
        sync_connection.rollback()


@pytest.mark.integration
def test_head_removes_legacy_document_source_ownership(sync_connection: Connection) -> None:
    column_exists = sync_connection.execute(
        text(
            "SELECT EXISTS ("
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'documents' AND column_name = 'doc_source_id'"
            ")"
        )
    ).scalar_one()
    index_exists = sync_connection.execute(
        text("SELECT to_regclass('ix_documents_doc_source_id')")
    ).scalar_one()
    constraint_exists = sync_connection.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM pg_constraint "
            "WHERE conname = 'fk_documents_doc_source_id_doc_sources')"
        )
    ).scalar_one()

    assert column_exists is False
    assert index_exists is None
    assert constraint_exists is False
    sync_connection.rollback()


@pytest.mark.integration
def test_orm_persists_and_deletes_active_source_version_graph(
    sync_connection: Connection,
) -> None:
    with Session(bind=sync_connection, expire_on_commit=False) as session:
        source = DocSource(
            source_type="github",
            source_config={"repository": "orm/project"},
            repository="orm/project",
            branch="main",
            path="docs",
            language="pt-BR",
            enabled=True,
        )
        version = SourceVersion(
            source=source,
            commit_sha="f" * 40,
            embedding_provider="local",
            embedding_model="hash",
            embedding_dimensions=1536,
            document_count=1,
            chunk_count=0,
        )
        document = Document(
            source_version=version,
            repository_path="docs/orm.md",
            source="github",
            source_url="https://example.test/orm",
            content="ORM cycle",
        )
        source.active_version = version
        session.add_all([source, document])
        session.flush()

        assert source.id is not None
        assert version.id is not None
        assert document.id is not None
        assert source.active_version_id == version.id
        assert document.source_version_id == version.id
        session.commit()

        source_id = source.id
        version_id = version.id
        document_id = document.id

        session.delete(source)
        session.commit()

    assert (
        sync_connection.execute(
            text("SELECT count(*) FROM doc_sources WHERE id = :source_id"),
            {"source_id": source_id},
        ).scalar_one()
        == 0
    )
    assert (
        sync_connection.execute(
            text("SELECT count(*) FROM source_versions WHERE id = :version_id"),
            {"version_id": version_id},
        ).scalar_one()
        == 0
    )
    assert (
        sync_connection.execute(
            text("SELECT count(*) FROM documents WHERE id = :document_id"),
            {"document_id": document_id},
        ).scalar_one()
        == 0
    )
    sync_connection.rollback()


@pytest.mark.integration
def test_source_identity_excludes_language(sync_connection: Connection) -> None:
    transaction = sync_connection.begin_nested()
    try:
        _insert_source(sync_connection)

        with pytest.raises(IntegrityError):
            with sync_connection.begin_nested():
                sync_connection.execute(
                    text(
                        "INSERT INTO doc_sources "
                        "(source_type, source_config, enabled, repository, branch, path, language) "
                        "VALUES ('github', '{}', true, 'example/project', 'main', "
                        "'docs', 'en')"
                    )
                )
    finally:
        transaction.rollback()
        sync_connection.rollback()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("embedding_dimensions", 0),
        ("document_count", -1),
        ("chunk_count", -1),
    ],
)
def test_source_version_rejects_invalid_counts(
    sync_connection: Connection, column: str, value: int
) -> None:
    transaction = sync_connection.begin_nested()
    try:
        source_id = _insert_source(sync_connection)
        statement = text(
            "INSERT INTO source_versions "
            "(source_id, commit_sha, embedding_provider, embedding_model, "
            "embedding_dimensions, document_count, chunk_count) "
            f"VALUES (:source_id, '{'b' * 40}', 'local', 'hash', "
            ":embedding_dimensions, :document_count, :chunk_count)"
        )
        values = {
            "source_id": source_id,
            "embedding_dimensions": 1536,
            "document_count": 0,
            "chunk_count": 0,
        }
        values[column] = value

        with pytest.raises(IntegrityError):
            with sync_connection.begin_nested():
                sync_connection.execute(statement, values)
    finally:
        transaction.rollback()
        sync_connection.rollback()


@pytest.mark.integration
def test_documents_are_unique_per_version_not_globally_by_url(
    sync_connection: Connection,
) -> None:
    transaction = sync_connection.begin_nested()
    try:
        source_id = _insert_source(sync_connection)
        first_version_id = _insert_version(sync_connection, source_id)
        second_version_id = _insert_version(sync_connection, source_id, commit_sha="b" * 40)
        insert_document = text(
            "INSERT INTO documents "
            "(source_version_id, repository_path, source, source_url, content) "
            "VALUES (:version_id, :path, 'github', 'https://example.test/shared', 'content')"
        )
        sync_connection.execute(
            insert_document,
            {"version_id": first_version_id, "path": "docs/guide.md"},
        )
        sync_connection.execute(
            insert_document,
            {"version_id": second_version_id, "path": "docs/guide.md"},
        )

        with pytest.raises(IntegrityError):
            with sync_connection.begin_nested():
                sync_connection.execute(
                    insert_document,
                    {"version_id": first_version_id, "path": "docs/guide.md"},
                )
    finally:
        transaction.rollback()
        sync_connection.rollback()


@pytest.mark.integration
def test_deleting_active_version_cascades_content_and_clears_pointer(
    sync_connection: Connection,
) -> None:
    transaction = sync_connection.begin_nested()
    try:
        source_id = _insert_source(sync_connection)
        version_id = _insert_version(sync_connection, source_id)
        sync_connection.execute(
            text("UPDATE doc_sources SET active_version_id = :version_id WHERE id = :source_id"),
            {"version_id": version_id, "source_id": source_id},
        )
        document_id = sync_connection.execute(
            text(
                "INSERT INTO documents "
                "(source_version_id, repository_path, source, source_url, content) "
                "VALUES (:version_id, 'docs/guide.md', 'github', "
                "'https://example.test/guide', 'content') RETURNING id"
            ),
            {"version_id": version_id},
        ).scalar_one()
        sync_connection.execute(
            text(
                "INSERT INTO document_chunks "
                "(document_id, chunk_text, chunk_index, chunk_hash, embedding, chunk_metadata) "
                "VALUES (:document_id, 'content', 0, :chunk_hash, "
                "CAST(:embedding AS vector), '{}')"
            ),
            {
                "document_id": document_id,
                "chunk_hash": "c" * 64,
                "embedding": "[" + ",".join(["0"] * 1536) + "]",
            },
        )

        sync_connection.execute(
            text("DELETE FROM source_versions WHERE id = :version_id"),
            {"version_id": version_id},
        )

        assert (
            sync_connection.execute(
                text("SELECT active_version_id FROM doc_sources WHERE id = :source_id"),
                {"source_id": source_id},
            ).scalar_one()
            is None
        )
        assert (
            sync_connection.execute(
                text("SELECT count(*) FROM documents WHERE id = :document_id"),
                {"document_id": document_id},
            ).scalar_one()
            == 0
        )
        assert (
            sync_connection.execute(
                text("SELECT count(*) FROM document_chunks WHERE document_id = :document_id"),
                {"document_id": document_id},
            ).scalar_one()
            == 0
        )
    finally:
        transaction.rollback()
        sync_connection.rollback()


@pytest.mark.integration
def test_deleting_source_cascades_versions(sync_connection: Connection) -> None:
    transaction = sync_connection.begin_nested()
    try:
        source_id = _insert_source(sync_connection)
        version_id = _insert_version(sync_connection, source_id)
        sync_connection.execute(
            text("UPDATE doc_sources SET active_version_id = :version_id WHERE id = :source_id"),
            {"version_id": version_id, "source_id": source_id},
        )

        sync_connection.execute(
            text("DELETE FROM doc_sources WHERE id = :source_id"),
            {"source_id": source_id},
        )

        assert (
            sync_connection.execute(
                text("SELECT count(*) FROM source_versions WHERE id = :version_id"),
                {"version_id": version_id},
            ).scalar_one()
            == 0
        )
    finally:
        transaction.rollback()
        sync_connection.rollback()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_promotion_retains_five_versions_and_retrieves_only_latest_snapshot(
    sync_connection: Connection,
) -> None:
    vector = [1.0] + [0.0] * 1535
    with Session(bind=sync_connection, expire_on_commit=False) as db_session:
        session = AsyncSessionFacade(db_session)
        source = await get_or_create_doc_source(
            session,
            repository="retention/project",
            branch="main",
            path="docs",
        )
        versions: list[SourceVersion] = []

        for index in range(1, 7):
            commit_sha = f"{index:040x}"
            repository_path = "docs/current.md" if index == 6 else "docs/removed.md"
            document = SourceVersionDocument(
                repository_path=repository_path,
                source="github",
                source_url=(
                    f"https://github.com/retention/project/blob/{commit_sha}/{repository_path}"
                ),
                title=f"Version {index}",
                content=f"Version {index} content",
                metadata={"commit_sha": commit_sha, "path": repository_path},
                chunks=[
                    Chunk(
                        text=f"Version {index} content",
                        index=0,
                        metadata={"source_path": repository_path},
                        content_hash=f"{index:064x}",
                    )
                ],
                embeddings=[vector],
            )
            version = await create_source_version_with_documents(
                session,
                source=source,
                commit_sha=commit_sha,
                embedding_provider="local",
                embedding_model="hash",
                embedding_dimensions=1536,
                documents=[document],
            )
            await promote_source_version(session, source=source, version=version)
            versions.append(version)

        db_session.flush()
        retained_ids = set(
            db_session.scalars(
                select(SourceVersion.id).where(SourceVersion.source_id == source.id)
            ).all()
        )
        active_paths = set(
            db_session.scalars(
                select(Document.repository_path).where(
                    Document.source_version_id == source.active_version_id
                )
            ).all()
        )
        chunks = await retrieve_chunks(
            session,
            question="active",
            embedding=vector,
            top_k=10,
            candidate_k=20,
            rrf_k=60,
            vector_weight=0.7,
            text_weight=0.3,
            source="github",
        )

        assert len(retained_ids) == 5
        assert versions[0].id not in retained_ids
        assert versions[-1].id in retained_ids
        assert source.active_version_id == versions[-1].id
        assert source.last_sync == versions[-1].synced_at
        assert active_paths == {"docs/current.md"}
        assert [chunk.source_url for chunk in chunks] == [
            f"https://github.com/retention/project/blob/{versions[-1].commit_sha}/docs/current.md"
        ]

        db_session.rollback()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_concurrent_source_creation_returns_single_source(
    sync_connection: Connection,
) -> None:
    assert sync_connection is not None
    test_database_url = os.environ["TEST_DATABASE_URL"]
    async_url = make_url(test_database_url).set(drivername="postgresql+asyncpg")
    engine = create_async_engine(async_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def create_source() -> int:
        async with session_factory() as session:
            source = await get_or_create_doc_source(
                session,
                repository="concurrent/project",
                branch="main",
                path="docs",
            )
            source_id = source.id
            await session.commit()
            return source_id

    try:
        source_ids = await asyncio.gather(create_source(), create_source())
        assert source_ids[0] == source_ids[1]

        async with session_factory() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(DocSource)
                .where(
                    DocSource.repository == "concurrent/project",
                    DocSource.branch == "main",
                    DocSource.path == "docs",
                )
            )
            assert count == 1
            await session.execute(delete(DocSource).where(DocSource.id == source_ids[0]))
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_source_row_lock_blocks_then_refreshes_updated_state(
    sync_connection: Connection,
) -> None:
    assert sync_connection is not None
    async_url = make_url(os.environ["TEST_DATABASE_URL"]).set(drivername="postgresql+asyncpg")
    engine = create_async_engine(async_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as setup:
            source = await get_or_create_doc_source(
                setup,
                repository="locking/project",
                branch="main",
                path="docs",
            )
            source_id = source.id
            await setup.commit()

        async with session_factory() as first, session_factory() as second:
            locked = await get_doc_source_for_update(first, source_id=source_id)
            assert locked is not None

            await second.execute(text("SET LOCAL lock_timeout = '100ms'"))
            with pytest.raises(DBAPIError) as exc_info:
                await get_doc_source_for_update(second, source_id=source_id)
            assert "lock timeout" in str(exc_info.value).lower()
            await second.rollback()

            locked.enabled = False
            await first.commit()

            refreshed = await get_doc_source_for_update(second, source_id=source_id)
            assert refreshed is not None
            assert refreshed.enabled is False
            await second.rollback()

        async with session_factory() as cleanup:
            await cleanup.execute(delete(DocSource).where(DocSource.id == source_id))
            await cleanup.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_real_revalidation_rejects_stale_promotion(
    sync_connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert sync_connection is not None
    async_url = make_url(os.environ["TEST_DATABASE_URL"]).set(drivername="postgresql+asyncpg")
    engine = create_async_engine(async_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    old_sha = "1" * 40
    newer_sha = "2" * 40
    stale_sha = "3" * 40
    newer_version_id: int | None = None

    async def promote_newer_version(*args: object, **kwargs: object) -> list[SimpleNamespace]:
        nonlocal newer_version_id
        async with session_factory() as competitor:
            source = await competitor.scalar(
                select(DocSource).where(DocSource.repository == "revalidation/project")
            )
            assert source is not None
            locked = await get_doc_source_for_update(competitor, source_id=source.id)
            assert locked is not None
            version = await create_source_version_with_documents(
                competitor,
                source=locked,
                commit_sha=newer_sha,
                embedding_provider="local",
                embedding_model="hash",
                embedding_dimensions=1536,
                documents=[],
            )
            await promote_source_version(competitor, source=locked, version=version)
            newer_version_id = version.id
            await competitor.commit()
        return [
            SimpleNamespace(
                path="docs/index.md",
                html_url=f"https://github.com/revalidation/project/blob/{stale_sha}/docs/index.md",
                sha="4" * 40,
                content="# Stale snapshot",
            )
        ]

    github = SimpleNamespace(
        get_repo=AsyncMock(
            return_value=SimpleNamespace(full_name="revalidation/project", default_branch="main")
        ),
        resolve_commit=AsyncMock(return_value=stale_sha),
        fetch_markdown_files=AsyncMock(side_effect=promote_newer_version),
        close=AsyncMock(),
    )
    monkeypatch.setattr(pipeline, "GithubClient", lambda _settings: github)
    embeddings = SimpleNamespace(
        dimensions=1536,
        embed_texts=AsyncMock(return_value=[[1.0] + [0.0] * 1535]),
    )
    settings = SimpleNamespace(
        embedding_provider="local",
        openai_embedding_model="text-embedding-3-small",
    )

    try:
        async with session_factory() as setup:
            source = await get_or_create_doc_source(
                setup,
                repository="revalidation/project",
                branch="main",
                path="docs",
            )
            old_version = await create_source_version_with_documents(
                setup,
                source=source,
                commit_sha=old_sha,
                embedding_provider="local",
                embedding_model="hash",
                embedding_dimensions=1536,
                documents=[],
            )
            await promote_source_version(setup, source=source, version=old_version)
            source_id = source.id
            await setup.commit()

        async with session_factory() as stale_session:
            with pytest.raises(pipeline.SourceSynchronizationConflict):
                await pipeline.ingest_github_repository(
                    stale_session,
                    settings=settings,
                    embeddings=embeddings,
                    repo_url="https://github.com/revalidation/project",
                    branch="main",
                    path="docs",
                    max_files=50,
                )

        async with session_factory() as verification:
            source = await verification.get(DocSource, source_id)
            assert source is not None
            assert source.active_version_id == newer_version_id
            stale_count = await verification.scalar(
                select(func.count())
                .select_from(SourceVersion)
                .where(
                    SourceVersion.source_id == source_id,
                    SourceVersion.commit_sha == stale_sha,
                )
            )
            assert stale_count == 0
            await verification.execute(delete(DocSource).where(DocSource.id == source_id))
            await verification.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_failed_first_preparation_does_not_create_source(
    sync_connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert sync_connection is not None
    async_url = make_url(os.environ["TEST_DATABASE_URL"]).set(drivername="postgresql+asyncpg")
    engine = create_async_engine(async_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    commit_sha = "5" * 40
    github = SimpleNamespace(
        get_repo=AsyncMock(
            return_value=SimpleNamespace(full_name="failed/project", default_branch="main")
        ),
        resolve_commit=AsyncMock(return_value=commit_sha),
        fetch_markdown_files=AsyncMock(
            return_value=[
                SimpleNamespace(
                    path="docs/index.md",
                    html_url=(f"https://github.com/failed/project/blob/{commit_sha}/docs/index.md"),
                    sha="6" * 40,
                    content="# Fails before persistence",
                )
            ]
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr(pipeline, "GithubClient", lambda _settings: github)
    embeddings = SimpleNamespace(
        dimensions=1536,
        embed_texts=AsyncMock(side_effect=RuntimeError("embedding failure")),
    )
    settings = SimpleNamespace(
        embedding_provider="local",
        openai_embedding_model="text-embedding-3-small",
    )

    try:
        async with session_factory() as session:
            with pytest.raises(RuntimeError, match="embedding failure"):
                await pipeline.ingest_github_repository(
                    session,
                    settings=settings,
                    embeddings=embeddings,
                    repo_url="https://github.com/failed/project",
                    branch="main",
                    path="docs",
                    max_files=50,
                )

        async with session_factory() as verification:
            source_count = await verification.scalar(
                select(func.count())
                .select_from(DocSource)
                .where(DocSource.repository == "failed/project")
            )
            assert source_count == 0
    finally:
        await engine.dispose()
