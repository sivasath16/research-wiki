"""Add generation_status to wiki_pages

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-05 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE wikigenerationstatus AS ENUM ('pending', 'running', 'ready', 'failed');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.add_column(
        "wiki_pages",
        sa.Column(
            "generation_status",
            sa.Enum("pending", "running", "ready", "failed", name="wikigenerationstatus"),
            nullable=False,
            server_default="pending",
        ),
    )
    # Existing rows with content are already ready
    op.execute("UPDATE wiki_pages SET generation_status = 'ready' WHERE content_md IS NOT NULL")


def downgrade() -> None:
    op.drop_column("wiki_pages", "generation_status")
    op.execute("DROP TYPE wikigenerationstatus")
