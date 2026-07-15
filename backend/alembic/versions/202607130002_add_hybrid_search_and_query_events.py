"""add hybrid search and anonymous query events

Revision ID: 202607130002
Revises: 202607130001
Create Date: 2026-07-13 00:02:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202607130002"
down_revision: str | None = "202607130001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('portuguese', coalesce(chunk_text, ''))",
                persisted=True,
            ),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_document_chunks_search_vector_gin",
        "document_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )

    # Legacy rows contain visitor questions and answers, which the new privacy policy forbids.
    op.drop_table("queries")
    op.create_table(
        "query_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("retrieved_chunk_count", sa.Integer(), nullable=False),
        sa.Column(
            "source_ids",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'::integer[]"),
            nullable=False,
        ),
        sa.Column(
            "source_version_ids",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'::integer[]"),
            nullable=False,
        ),
        sa.Column("top_fused_score", sa.Float(), nullable=True),
        sa.Column("score_gap", sa.Float(), nullable=True),
        sa.Column("feedback", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('answered', 'insufficient_evidence')",
            name="ck_query_events_state",
        ),
        sa.CheckConstraint(
            "latency_ms >= 0",
            name="ck_query_events_latency_ms_nonnegative",
        ),
        sa.CheckConstraint(
            "retrieved_chunk_count >= 0",
            name="ck_query_events_retrieved_chunk_count_nonnegative",
        ),
        sa.CheckConstraint(
            "feedback IS NULL OR feedback IN (-1, 1)",
            name="ck_query_events_feedback",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("query_events")

    # Recreate the historical shape for migration reversibility; discarded content is not restored.
    op.create_table(
        "queries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_query", sa.Text(), nullable=False),
        sa.Column("retrieved_chunks_ids", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("llm_response", sa.Text(), nullable=False),
        sa.Column("user_feedback", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("retrieved_chunk_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.drop_index("ix_document_chunks_search_vector_gin", table_name="document_chunks")
    op.drop_column("document_chunks", "search_vector")
