"""Add semantic_cache table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-06 00:00:00.000000

Replaces Redis-based semantic cache with a pgvector table so similarity
search uses the HNSW index instead of a Python-side linear scan.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 768


def upgrade() -> None:
    op.create_table(
        "semantic_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("repo_id", sa.Integer(), sa.ForeignKey("repos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("query_intent", sa.String(20), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_semantic_cache_repo_created", "semantic_cache", ["repo_id", "created_at"])
    # HNSW index for fast ANN cosine similarity search
    op.execute(
        "CREATE INDEX ix_semantic_cache_embedding "
        "ON semantic_cache USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_table("semantic_cache")
