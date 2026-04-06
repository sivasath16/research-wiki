"""Initial schema with pgvector

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("login", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("email", sa.String(255)),
        sa.Column("avatar_url", sa.Text()),
        sa.Column("github_token_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("github_id"),
    )
    op.create_index("ix_users_github_id", "users", ["github_id"])

    op.create_table(
        "repos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("language", sa.String(100)),
        sa.Column("is_private", sa.Boolean(), default=False),
        sa.Column("last_commit_sha", sa.String(40)),
        sa.Column("indexed_at", sa.DateTime()),
        sa.Column(
            "index_status",
            sa.Enum("pending", "indexing", "ready", "stale", "failed", name="indexstatus"),
            nullable=False,
        ),
        sa.Column("chunk_count", sa.Integer(), default=0),
        sa.Column("file_count", sa.Integer(), default=0),
        sa.Column("error_message", sa.Text()),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_repos_user_id", "repos", ["user_id"])
    op.create_index("ix_repos_owner_name", "repos", ["owner", "name"])

    op.create_table(
        "wiki_pages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("repo_id", sa.Integer(), sa.ForeignKey("repos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("content_md", sa.Text()),
        sa.Column("mermaid_diagram", sa.Text()),
        sa.Column("generated_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wiki_pages_repo_path", "wiki_pages", ["repo_id", "path"], unique=True)

    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("repo_id", sa.Integer(), sa.ForeignKey("repos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(384)),
        sa.Column("chunk_type", sa.String(50)),
        sa.Column("name", sa.String(512)),
        sa.Column("start_line", sa.Integer()),
        sa.Column("end_line", sa.Integer()),
        sa.Column("language", sa.String(50)),
        sa.Column("metadata", sa.JSON(), default={}),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chunks_repo_id", "chunks", ["repo_id"])
    op.create_index("ix_chunks_file_path", "chunks", ["repo_id", "file_path"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("repo_id", sa.Integer(), sa.ForeignKey("repos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", name="jobstatus"),
            nullable=False,
        ),
        sa.Column("progress_step", sa.String(255)),
        sa.Column("progress_pct", sa.Float(), default=0.0),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("chunks")
    op.drop_table("wiki_pages")
    op.drop_table("repos")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS indexstatus")
    op.execute("DROP TYPE IF EXISTS jobstatus")
    op.execute("DROP EXTENSION IF EXISTS vector")
