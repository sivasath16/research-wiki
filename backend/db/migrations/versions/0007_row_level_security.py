"""Enable row-level security (tenant isolation by app.user_id GUC).

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-06 00:00:00.000000

Session code sets app.user_id (and app.service_mode during OAuth callback).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tenant id from set_config('app.user_id', ...) — empty string means unset.
_UID = "NULLIF(current_setting('app.user_id', true), '')::int"

def upgrade() -> None:
    # ── users ─────────────────────────────────────────────────────────────
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY users_select ON users FOR SELECT
        USING (id = {_UID} OR current_setting('app.service_mode', true) = 'on')
    """)
    op.execute("""
        CREATE POLICY users_insert ON users FOR INSERT
        WITH CHECK (current_setting('app.service_mode', true) = 'on')
    """)
    op.execute(f"""
        CREATE POLICY users_update ON users FOR UPDATE
        USING (id = {_UID} OR current_setting('app.service_mode', true) = 'on')
    """)
    op.execute(f"""
        CREATE POLICY users_delete ON users FOR DELETE
        USING (id = {_UID})
    """)

    # ── repos ─────────────────────────────────────────────────────────────
    op.execute("ALTER TABLE repos ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE repos FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY repos_isolation ON repos FOR ALL
        USING (user_id = {_UID})
        WITH CHECK (user_id = {_UID})
    """)

    # ── jobs ──────────────────────────────────────────────────────────────
    op.execute("ALTER TABLE jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE jobs FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY jobs_isolation ON jobs FOR ALL
        USING (user_id = {_UID})
        WITH CHECK (user_id = {_UID})
    """)

    # ── chunks (via repo ownership) ───────────────────────────────────────
    op.execute("ALTER TABLE chunks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE chunks FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY chunks_isolation ON chunks FOR ALL
        USING (
          EXISTS (
            SELECT 1 FROM repos r
            WHERE r.id = chunks.repo_id AND r.user_id = {_UID}
          )
        )
        WITH CHECK (
          EXISTS (
            SELECT 1 FROM repos r
            WHERE r.id = chunks.repo_id AND r.user_id = {_UID}
          )
        )
    """)

    # ── wiki_pages ─────────────────────────────────────────────────────────
    op.execute("ALTER TABLE wiki_pages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE wiki_pages FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY wiki_pages_isolation ON wiki_pages FOR ALL
        USING (
          EXISTS (
            SELECT 1 FROM repos r
            WHERE r.id = wiki_pages.repo_id AND r.user_id = {_UID}
          )
        )
        WITH CHECK (
          EXISTS (
            SELECT 1 FROM repos r
            WHERE r.id = wiki_pages.repo_id AND r.user_id = {_UID}
          )
        )
    """)

    # ── semantic_cache ────────────────────────────────────────────────────
    op.execute("ALTER TABLE semantic_cache ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE semantic_cache FORCE ROW LEVEL SECURITY")
    op.execute(f"""
        CREATE POLICY semantic_cache_isolation ON semantic_cache FOR ALL
        USING (
          EXISTS (
            SELECT 1 FROM repos r
            WHERE r.id = semantic_cache.repo_id AND r.user_id = {_UID}
          )
        )
        WITH CHECK (
          EXISTS (
            SELECT 1 FROM repos r
            WHERE r.id = semantic_cache.repo_id AND r.user_id = {_UID}
          )
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS semantic_cache_isolation ON semantic_cache")
    op.execute("DROP POLICY IF EXISTS wiki_pages_isolation ON wiki_pages")
    op.execute("DROP POLICY IF EXISTS chunks_isolation ON chunks")
    op.execute("DROP POLICY IF EXISTS jobs_isolation ON jobs")
    op.execute("DROP POLICY IF EXISTS repos_isolation ON repos")
    op.execute("DROP POLICY IF EXISTS users_select ON users")
    op.execute("DROP POLICY IF EXISTS users_insert ON users")
    op.execute("DROP POLICY IF EXISTS users_update ON users")
    op.execute("DROP POLICY IF EXISTS users_delete ON users")

    for table in (
        "semantic_cache",
        "wiki_pages",
        "chunks",
        "jobs",
        "repos",
        "users",
    ):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
