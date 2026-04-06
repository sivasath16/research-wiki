"""Add wiki_structure to repos

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-05 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("repos", sa.Column("wiki_structure", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("repos", "wiki_structure")
