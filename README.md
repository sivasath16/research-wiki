# ResearchWiki

A production-grade DeepWiki clone for university research groups. Index GitHub repos and chat with your codebase using AI.

## Stack

- **Frontend**: Next.js + Tailwind CSS
- **Backend**: FastAPI + Celery + Redis
- **Database**: PostgreSQL 16 + pgvector (HNSW index)
- **Auth**: GitHub OAuth 2.0 (httpOnly cookie session)
- **LLM**: Anthropic Claude — Haiku for ingestion/re-ranking, Sonnet for chat
- **Embeddings**: sentence-transformers `all-MiniLM-L6-v2` (local, no API cost)

## Quick Start

### 1. Create GitHub OAuth App

Go to https://github.com/settings/developers → **New OAuth App**:
- Homepage URL: `http://localhost:3000`
- Authorization callback URL: `http://localhost:3000/auth/callback`

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:
```
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret
ANTHROPIC_API_KEY=sk-ant-...
FERNET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```

### 3. Start services

```bash
docker compose up --build
```

Services start in order: postgres → redis → backend (migrations run) → celery-worker → frontend.

- Frontend: http://localhost:3000
- API: http://localhost:8001
- Flower (Celery monitor): http://localhost:5555

### 4. Run migrations (first time)

```bash
docker compose exec backend alembic upgrade head
```

## Architecture

```
frontend (React)  →  FastAPI  →  PostgreSQL (pgvector)
                      ↓
                   Celery Worker
                      ├── tree-sitter chunking
                      ├── sentence-transformers embeddings
                      └── Claude Haiku wiki generation

WebSocket /ws/chat/{repo_id}
  → embed query (local)
  → pgvector cosine search (top 20)
  → Claude Haiku re-rank (top 5)
  → Claude Sonnet streaming answer
```

## Ingestion Pipeline

1. **Clone** — `git clone --depth=1` via GitHub API token
2. **Walk** — skip node_modules, dist, binaries, files >500KB/>10k lines
3. **Chunk** — tree-sitter AST at function/class boundaries; sliding window for markdown/yaml
4. **Embed** — `all-MiniLM-L6-v2` locally, batch size 64, 384-dim vectors
5. **Insert** — bulk insert into `chunks` table with pgvector
6. **Index** — HNSW index `(m=16, ef_construction=64)` after bulk insert
7. **Wiki** — lazily generated per directory on first visit (Claude Haiku)
8. **Mermaid** — top-level architecture diagram generated at index time

## Rate Limiting

- 20 chat queries per user per day
- Redis key: `ratelimit:{user_id}:{date}`, TTL 24h
- Remaining count returned in every WebSocket message

## Stale Detection

On `GET /api/repos/{id}`, a background task checks the latest commit SHA via GitHub API. If it differs from the stored SHA, the repo is marked `stale`. The wiki shows an amber banner prompting re-index.

## Development

Run backend only (no Docker):

```bash
cd backend
pip install -r requirements.txt
DATABASE_URL=postgresql://... REDIS_URL=redis://... uvicorn api.main:app --reload --port 8001
```

Run Celery worker:

```bash
cd backend
celery -A worker.celery_app worker --concurrency=2 --loglevel=info
```

Run frontend:

```bash
cd frontend
npm install
npm run dev
```
