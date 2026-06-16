"""add chunk hashes

Revision ID: 202606160001
Revises: 202606150001
Create Date: 2026-06-16 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202606160001"
down_revision: str | None = "202606150001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("chunk_hash", sa.String(length=64), nullable=True))
    op.execute(
        """
        UPDATE document_chunks
        SET chunk_hash = md5(regexp_replace(chunk_text, '\\s+', ' ', 'g'))
        """
    )
    op.execute(
        """
        DELETE FROM document_chunks duplicate
        USING document_chunks original
        WHERE duplicate.document_id = original.document_id
          AND duplicate.chunk_hash = original.chunk_hash
          AND duplicate.id > original.id
        """
    )
    op.alter_column(
        "document_chunks",
        "chunk_hash",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.create_index(
        "ix_document_chunks_document_hash",
        "document_chunks",
        ["document_id", "chunk_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_document_hash", table_name="document_chunks")
    op.drop_column("document_chunks", "chunk_hash")
