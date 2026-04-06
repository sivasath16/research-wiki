from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from starlette.requests import HTTPConnection

from core.config import settings
from core.session_cookie import try_session_user_id
from db.rls_context import rls_oauth_service, rls_user_id

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(OrmSession, "after_begin", propagate=True)
def _apply_rls_on_transaction_begin(session, transaction, connection, parent=None):
    """
    Apply RLS GUCs per transaction.

    Prefer Session.info (set by get_db) so FastAPI's threadpool for sync deps does not
    break ContextVar reset. Celery and other sync code use user_rls() ContextVars.
    """
    oauth = session.info.get("rls_oauth_service")
    if oauth is None:
        oauth = rls_oauth_service.get()
    if oauth:
        connection.execute(text("SELECT set_config('app.service_mode', 'on', true)"))
        return

    uid = session.info.get("rls_user_id")
    if uid is None:
        uid = rls_user_id.get()
    if uid is None:
        connection.execute(text("SELECT set_config('app.user_id', '', true)"))
    else:
        connection.execute(
            text("SELECT set_config('app.user_id', :uid, true)"),
            {"uid": str(uid)},
        )


def get_db(conn: HTTPConnection):
    token = conn.cookies.get("session")
    uid = try_session_user_id(token)
    db = SessionLocal()
    # Bound to this Session so RLS works when Depends(get_db) runs in a worker thread
    # (ContextVar set/reset can span contexts; see PEP 567 + FastAPI threadpool).
    db.info["rls_user_id"] = uid
    db.info["rls_oauth_service"] = getattr(conn.state, "rls_oauth_service", False)
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables and indexes if they don't exist. Called on app startup."""
    from db.models import Base, EMBEDDING_DIM
    from sqlalchemy import text
    import logging
    logger = logging.getLogger(__name__)

    # If embedding dimension changed (e.g. upgrading from 384 → 768),
    # drop chunks so create_all recreates it with the correct vector size.
    with engine.connect() as conn:
        try:
            result = conn.execute(text(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
            )).fetchone()
            if result is not None:
                # pgvector stores dim as (dim + 1) in atttypmod
                current_dim = result[0] - 1
                if current_dim != EMBEDDING_DIM:
                    raise RuntimeError(
                        f"Embedding dimension mismatch: database has {current_dim}D vectors, "
                        f"code expects {EMBEDDING_DIM}D. "
                        f"Run `alembic upgrade head` or manually drop the chunks table "
                        f"after backing up data. Never drops automatically."
                    )
        except Exception:
            pass  # Table doesn't exist yet — create_all handles it

    Base.metadata.create_all(bind=engine)

    # Vector HNSW indexes are created by Alembic (0003 chunks, 0006 semantic_cache).
    # Do not CREATE INDEX here: with FORCE ROW LEVEL SECURITY, the app role cannot
    # build indexes over tenant data without a matching RLS context.
