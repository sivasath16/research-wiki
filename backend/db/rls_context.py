"""
Per-task / per-request tenant context for PostgreSQL RLS (app.user_id, app.service_mode).

`db.session` registers an `after_begin` listener on SQLAlchemy Session so every new
transaction applies the right GUCs — you do not call set_config by hand except in tests.

Usage:
  - HTTP/WebSocket: `get_db` sets `Session.info["rls_user_id"]` and optional
    `Session.info["rls_oauth_service"]` from the cookie + `request.state` (avoids
    ContextVar issues when FastAPI runs sync `Depends` in a thread pool).
  - OAuth callback: `Depends(oauth_rls_dependency)` sets `request.state.rls_oauth_service`.
  - Celery / background: `with user_rls(user_id):` around `SessionLocal()` usage (ContextVar).
"""
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

from starlette.requests import Request

# Logged-in user id for Celery / sync paths without Session.info (see session.py).
rls_user_id: ContextVar[int | None] = ContextVar("rls_user_id", default=None)

# Trusted OAuth upsert path when not using get_db Session.info.
rls_oauth_service: ContextVar[bool] = ContextVar("rls_oauth_service", default=False)


@contextmanager
def user_rls(user_id: int | None) -> Iterator[None]:
    """Set tenant id for the current sync context (Celery tasks, background threads, etc.)."""
    tok: Token = rls_user_id.set(user_id)
    try:
        yield
    finally:
        rls_user_id.reset(tok)


def oauth_rls_dependency(request: Request):
    """FastAPI dependency: run before get_db on /api/auth/callback."""
    request.state.rls_oauth_service = True
    yield
