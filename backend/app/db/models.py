from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID as UUIDValue

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
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
        Index(
            "ix_document_chunks_search_vector_gin",
            "search_vector",
            postgresql_using="gin",
        ),
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
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('portuguese', coalesce(chunk_text, ''))",
            persisted=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="chunks")


class QueryEvent(Base):
    __tablename__ = "query_events"
    __table_args__ = (
        CheckConstraint(
            "state IN ('answered', 'insufficient_evidence')",
            name="ck_query_events_state",
        ),
        CheckConstraint(
            "latency_ms >= 0",
            name="ck_query_events_latency_ms_nonnegative",
        ),
        CheckConstraint(
            "retrieved_chunk_count >= 0",
            name="ck_query_events_retrieved_chunk_count_nonnegative",
        ),
        CheckConstraint(
            "feedback IS NULL OR feedback IN (-1, 1)",
            name="ck_query_events_feedback",
        ),
    )

    id: Mapped[UUIDValue] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieved_chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, server_default="{}", nullable=False
    )
    source_version_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, server_default="{}", nullable=False
    )
    top_fused_score: Mapped[float | None] = mapped_column(Float)
    score_gap: Mapped[float | None] = mapped_column(Float)
    feedback: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


@dataclass
class QueryLog:
    """Unmapped Sprint 02 compatibility object; query content cannot persist at schema head."""

    id: int = 0
    user_query: str = ""
    retrieved_chunks_ids: list[int] | None = None
    llm_response: str = ""
    user_feedback: int | None = None
    latency_ms: int = 0
    retrieved_chunk_count: int = 0
    created_at: datetime | None = None


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
