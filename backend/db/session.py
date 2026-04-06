from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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

    # HNSW index — created once here, never inside ingest tasks
    with engine.connect() as conn:
        conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
            ON chunks USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
        """))
        conn.commit()


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
