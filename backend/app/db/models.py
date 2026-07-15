from datetime import datetime
from typing import Any, ClassVar

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("source_version_id", "repository_path", name="uq_documents_version_path"),
    )

    # Temporary non-persisted input for the pre-version repository API removed in Task 3.
    doc_source_id: ClassVar[int | None] = None

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_version_id: Mapped[int] = mapped_column(
        ForeignKey(
            "source_versions.id",
            name="fk_documents_source_version_id_source_versions",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    repository_path: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    doc_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    source_version: Mapped["SourceVersion"] = relationship(back_populates="documents")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_document_hash", "document_id", "chunk_hash", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(get_settings().embedding_dimensions), nullable=False
    )
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="chunks")


class QueryLog(Base):
    __tablename__ = "queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_chunks_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    llm_response: Mapped[str] = mapped_column(Text, nullable=False)
    user_feedback: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retrieved_chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocSource(Base):
    __tablename__ = "doc_sources"
    __table_args__ = (
        UniqueConstraint(
            "repository", "branch", "path", name="uq_doc_sources_repository_branch_path"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    repository: Mapped[str] = mapped_column(String(255), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    active_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "source_versions.id",
            name="fk_doc_sources_active_version_id_source_versions",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
        index=True,
    )
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    versions: Mapped[list["SourceVersion"]] = relationship(
        back_populates="source",
        foreign_keys="SourceVersion.source_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    active_version: Mapped["SourceVersion | None"] = relationship(
        foreign_keys=[active_version_id], post_update=True
    )


class SourceVersion(Base):
    __tablename__ = "source_versions"
    __table_args__ = (
        CheckConstraint(
            "embedding_dimensions > 0",
            name="ck_source_versions_embedding_dimensions_positive",
        ),
        CheckConstraint(
            "document_count >= 0", name="ck_source_versions_document_count_nonnegative"
        ),
        CheckConstraint("chunk_count >= 0", name="ck_source_versions_chunk_count_nonnegative"),
        UniqueConstraint("source_id", "commit_sha", name="uq_source_versions_source_commit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey(
            "doc_sources.id",
            name="fk_source_versions_source_id_doc_sources",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    embedding_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)

    source: Mapped[DocSource] = relationship(back_populates="versions", foreign_keys=[source_id])
    documents: Mapped[list[Document]] = relationship(
        back_populates="source_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
