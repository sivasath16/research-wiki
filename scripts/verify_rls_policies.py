#!/usr/bin/env python3
"""
Fail if public tables are missing RLS policies (Postgres defense-in-depth checklist).

Usage (from repo root, with DATABASE_URL set):
  python scripts/verify_rls_policies.py
"""
from __future__ import annotations

import os
import sys

REQUIRED_TABLES = frozenset(
    {"users", "repos", "jobs", "chunks", "wiki_pages", "semantic_cache"}
)


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        print("sqlalchemy is required (install backend requirements)", file=sys.stderr)
        return 2

    engine = create_engine(url)
    bad: list[str] = []

    with engine.connect() as conn:
        for name in sorted(REQUIRED_TABLES):
            row = conn.execute(
                text(
                    """
                    SELECT c.relrowsecurity, c.relforcerowsecurity
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.relkind = 'r'
                      AND c.relname = :t
                    """
                ),
                {"t": name},
            ).fetchone()
            if row is None:
                bad.append(f"{name} (table missing)")
                continue
            enabled, forced = row[0], row[1]
            if not enabled or not forced:
                bad.append(f"{name} (rowsecurity={enabled}, forcerowsecurity={forced})")

            n_pol = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM pg_policies
                    WHERE schemaname = 'public' AND tablename = :t
                    """
                ),
                {"t": name},
            ).scalar()
            if not n_pol:
                bad.append(f"{name} (no rows in pg_policies)")

    if bad:
        print("RLS check failed:", file=sys.stderr)
        for line in bad:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print("RLS OK:", ", ".join(sorted(REQUIRED_TABLES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
