"""link documents to sources

Revision ID: 202606170002
Revises: 202606170001
Create Date: 2026-06-17 00:02:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202606170002"
down_revision: str | None = "202606170001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("doc_source_id", sa.Integer(), nullable=True))
    op.create_index("ix_documents_doc_source_id", "documents", ["doc_source_id"])
    op.create_foreign_key(
        "fk_documents_doc_source_id_doc_sources",
        "documents",
        "doc_sources",
        ["doc_source_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_documents_doc_source_id_doc_sources", "documents", type_="foreignkey")
    op.drop_index("ix_documents_doc_source_id", table_name="documents")
    op.drop_column("documents", "doc_source_id")
