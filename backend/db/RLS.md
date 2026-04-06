# PostgreSQL row-level security (RLS)

## How tenant context is applied

1. **HTTP/WebSocket** (`db/session.py`): `get_db` sets `Session.info` (`rls_user_id`, `rls_oauth_service`) from the session cookie and `request.state` so RLS works when FastAPI runs sync `Depends` in a thread pool.
2. **Celery / sync workers** (`db/rls_context.py`): `with user_rls(user_id):` uses ContextVars read by `after_begin` when `Session.info` keys are absent.
3. **SQLAlchemy** `Session.after_begin`: every new ORM transaction runs `set_config('app.user_id', …)` or `app.service_mode` from `Session.info` first, then ContextVars.
4. **OAuth callback**: `Depends(oauth_rls_dependency)` sets `request.state.rls_oauth_service` before `Depends(get_db)`.

Do **not** open a `SessionLocal()` without `get_db` / `user_rls` / OAuth path above (unless you are a superuser migration).

## Adding a new table

1. Add the SQLAlchemy model and migration `CREATE TABLE`.
2. In the **same** Alembic revision (or a follow-up): `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, and policies that tie rows to `app.user_id` (directly or via `repos.user_id`).
3. Run `python scripts/verify_rls_policies.py` (from repo root) against your DB to confirm every tenant table is covered.

## Optional hardening

- **CI**: run `verify_rls_policies.py` after migrations in staging.
- **Code review**: grep for `SessionLocal(` outside `user_rls` / `get_db` / tests.
