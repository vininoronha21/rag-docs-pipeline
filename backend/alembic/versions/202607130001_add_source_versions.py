"""add source versions

Revision ID: 202607130001
Revises: 202606170002
Create Date: 2026-07-13 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607130001"
down_revision: str | None = "202606170002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Legacy mutable rows cannot be assigned an honest historical commit SHA.
    op.execute("DELETE FROM document_chunks")
    op.execute("DELETE FROM documents")
    op.execute("DELETE FROM doc_sources")

    op.add_column("doc_sources", sa.Column("repository", sa.String(length=255), nullable=False))
    op.add_column("doc_sources", sa.Column("branch", sa.String(length=255), nullable=False))
    op.add_column("doc_sources", sa.Column("path", sa.Text(), nullable=False))
    op.add_column("doc_sources", sa.Column("language", sa.String(length=16), nullable=False))
    op.create_unique_constraint(
        "uq_doc_sources_repository_branch_path",
        "doc_sources",
        ["repository", "branch", "path"],
    )

    op.create_table(
        "source_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("embedding_provider", sa.String(length=50), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "embedding_dimensions > 0",
            name="ck_source_versions_embedding_dimensions_positive",
        ),
        sa.CheckConstraint(
            "document_count >= 0",
            name="ck_source_versions_document_count_nonnegative",
        ),
        sa.CheckConstraint(
            "chunk_count >= 0",
            name="ck_source_versions_chunk_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["doc_sources.id"],
            name="fk_source_versions_source_id_doc_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "commit_sha",
            name="uq_source_versions_source_commit",
        ),
    )
    op.create_index("ix_source_versions_source_id", "source_versions", ["source_id"])

    op.add_column("doc_sources", sa.Column("active_version_id", sa.Integer(), nullable=True))
    op.create_index("ix_doc_sources_active_version_id", "doc_sources", ["active_version_id"])
    op.create_foreign_key(
        "fk_doc_sources_active_version_id_source_versions",
        "doc_sources",
        "source_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint("documents_source_url_key", "documents", type_="unique")
    op.add_column("documents", sa.Column("source_version_id", sa.Integer(), nullable=False))
    op.add_column("documents", sa.Column("repository_path", sa.Text(), nullable=False))
    op.create_index("ix_documents_source_version_id", "documents", ["source_version_id"])
    op.create_foreign_key(
        "fk_documents_source_version_id_source_versions",
        "documents",
        "source_versions",
        ["source_version_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_documents_version_path",
        "documents",
        ["source_version_id", "repository_path"],
    )


def downgrade() -> None:
    # Destructive by design: versioned rows may violate legacy global URL uniqueness.
    op.execute("DELETE FROM document_chunks")
    op.execute("DELETE FROM documents")

    op.drop_constraint("uq_documents_version_path", "documents", type_="unique")
    op.drop_constraint(
        "fk_documents_source_version_id_source_versions",
        "documents",
        type_="foreignkey",
    )
    op.drop_index("ix_documents_source_version_id", table_name="documents")
    op.drop_column("documents", "repository_path")
    op.drop_column("documents", "source_version_id")
    op.create_unique_constraint("documents_source_url_key", "documents", ["source_url"])

    op.drop_constraint(
        "fk_doc_sources_active_version_id_source_versions",
        "doc_sources",
        type_="foreignkey",
    )
    op.drop_index("ix_doc_sources_active_version_id", table_name="doc_sources")
    op.drop_column("doc_sources", "active_version_id")

    op.drop_index("ix_source_versions_source_id", table_name="source_versions")
    op.drop_table("source_versions")

    op.drop_constraint("uq_doc_sources_repository_branch_path", "doc_sources", type_="unique")
    op.drop_column("doc_sources", "language")
    op.drop_column("doc_sources", "path")
    op.drop_column("doc_sources", "branch")
    op.drop_column("doc_sources", "repository")
