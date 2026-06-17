"""add query metrics

Revision ID: 202606170001
Revises: 202606160001
Create Date: 2026-06-17 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202606170001"
down_revision: str | None = "202606160001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "queries",
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "queries",
        sa.Column("retrieved_chunk_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        """
        UPDATE queries
        SET retrieved_chunk_count = COALESCE(cardinality(retrieved_chunks_ids), 0)
        """
    )
    op.alter_column("queries", "latency_ms", server_default=None)
    op.alter_column("queries", "retrieved_chunk_count", server_default=None)


def downgrade() -> None:
    op.drop_column("queries", "retrieved_chunk_count")
    op.drop_column("queries", "latency_ms")
