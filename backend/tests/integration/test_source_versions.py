import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import DocSource, Document, SourceVersion


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
