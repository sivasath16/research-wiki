# ResearchWiki

A production-grade DeepWiki-style app for research groups: index GitHub repos, browse an AI-generated wiki, and chat over the codebase with retrieval-augmented generation (RAG).

## Stack

- **Frontend**: React + Vite (app in `frontend/`) + Tailwind CSS
- **Edge**: nginx — TLS termination, rate limits, WebSocket proxy to the API
- **Backend**: FastAPI (Gunicorn + Uvicorn workers)
- **Jobs**: Celery with **RabbitMQ** as the broker and **Redis** for results, OAuth state, rate limiting, and wiki task deduplication
- **Database**: PostgreSQL 16 + pgvector (cosine / HNSW)
- **Tenant isolation**: PostgreSQL row-level security (RLS) with per-request `app.user_id` context — see `backend/db/RLS.md`
- **Auth**: GitHub OAuth 2.0; session via signed **httpOnly** cookie (`backend/core/session_cookie.py`)
- **LLM** (configurable in `backend/core/config.py`): Anthropic **Claude Haiku** (query condensation, wiki planning, architecture diagram, wiki page copy) and **Claude Sonnet** (streaming chat answers)
- **Embeddings**: `jinaai/jina-embeddings-v2-base-code` via sentence-transformers (local, 768-dimensional vectors)
- **Reranking**: cross-encoder `cross-encoder/ms-marco-MiniLM-L-6-v2` (local; replaces an older LLM-based rerank path)

## Quick Start

### 1. Create a GitHub OAuth App

Go to https://github.com/settings/developers → **New OAuth App**.

- **Homepage URL**: your app origin (e.g. `https://localhost` when using the bundled nginx TLS setup, or `http://localhost:3000` for a minimal local frontend-only URL).
- **Authorization callback URL**: must match **`GITHUB_CALLBACK_URL`** exactly (see below), e.g. `https://localhost/api/auth/callback`.

### 2. Configure environment

```bash
cp .env.example .env
```

Set at least:

| Variable | Purpose |
|----------|---------|
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | GitHub OAuth |
| `GITHUB_CALLBACK_URL` | OAuth redirect; default pattern `/api/auth/callback` under the API |
| `ANTHROPIC_API_KEY` | Claude API |
| `SECRET_KEY` | Session signing — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `FERNET_KEY` | Encrypts stored GitHub tokens — `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `REDIS_PASSWORD` | Redis auth (compose) |
| `RABBITMQ_PASSWORD` | RabbitMQ auth (**required** for `docker compose`; matches `RABBITMQ_URL` in services) |
| `FRONTEND_URL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL` | Browser → API / WebSocket URLs (use `wss://` behind HTTPS) |
| `FLOWER_USER`, `FLOWER_PASSWORD` | Celery Flower basic auth |

### 3. Start services

```bash
docker compose up --build
```

Typical layout:

| Service | Role |
|---------|------|
| `postgres` | App data + pgvector |
| `rabbitmq` | Celery AMQP broker |
| `redis` | Celery backend, rate limits, OAuth state, wiki dispatch keys |
| `backend` | FastAPI on `127.0.0.1:8001` |
| `celery-worker` | Queues `ingest`, `wiki` (ingestion + wiki page tasks) |
| `celery-flower` | Task UI on `127.0.0.1:5555` (basic auth) |
| `frontend` | Next.js on `127.0.0.1:3000` |
| `nginx` | HTTPS on `443` (certs in `nginx/certs/`; HTTP redirects to HTTPS) |

- **HTTPS app (via nginx)**: `https://localhost` — API under `/api/`, WebSocket chat under `/ws/`.
- **Direct API (dev)**: `http://127.0.0.1:8001`

### 4. Run database migrations

The API calls `init_db()` on startup (`create_all`), but **indexes, RLS, and other revisions are applied with Alembic**. After the first bring-up:

```bash
docker compose exec backend alembic upgrade head
```

## Architecture

```
Browser  →  nginx (TLS)  →  frontend (Next.js)
                │
                ├→ /api/* , /ws/*  →  backend (FastAPI)
                │                         │
                │                         ├→ PostgreSQL (pgvector, RLS)
                │                         └→ Redis (sessions/ratelimit/cache keys)
                │
Celery workers  ←→  RabbitMQ (broker)  +  Redis (result backend)
       │
       ├─ ingest queue: clone, chunk, embed, index repo, enqueue wiki jobs
       └─ wiki queue: generate wiki pages (Haiku), architecture Mermaid on overview
```

### Chat (WebSocket `WS /ws/chat/{repo_id}`)

1. Authenticate with the same session cookie as the REST API.
2. **Rate limit**: Redis counter per user per day (`ratelimit:{user_id}:{date}`); remaining count is included in stream messages.
3. Optional **multi-turn**: Haiku rewrites follow-ups into a standalone search query (`condense_query`).
4. **Intent** (heuristic): `usage` / `implementation` / `general` → filters chunk types.
5. **Retrieve**: embed query (Jina) → pgvector ANN on `chunks` (default top **20**).
6. **Cross-repo**: if the best score is low, suggest other indexed repos that match `Repo.dependencies`.
7. **Rerank**: cross-encoder keeps top **5** chunks.
8. **Context**: top wiki pages (keyword overlap) + code snippets → **Sonnet** streams the answer.
9. **Semantic cache**: similar past queries (embedding + Jaccard) can return a cached reply without calling Sonnet again.

## Ingestion pipeline (`ingest`)

1. **Clone** — shallow clone using the user’s GitHub token.
2. **Walk** — skip large/binary paths; limits configurable (`max_file_size_bytes`, `max_file_lines`, `max_repo_size_kb`).
3. **Chunk** — tree-sitter AST boundaries where possible; sliding windows for prose configs.
4. **Embed** — Jina model, batched (`embed_batch_size` from config, default 64).
5. **Insert** — bulk insert into `chunks` (768-d vectors).
6. **Index** — HNSW on `chunks.embedding` via migration (`m = 16`, `ef_construction = 64`). A separate HNSW index exists for semantic-cache embeddings.
7. **Wiki** — Haiku builds a wiki structure and overview; Mermaid diagram on overview when generation succeeds; each page is filled by Celery tasks on the **`wiki`** queue. Additional directory pages can still be requested on demand via the wiki API (tasks deduplicated with Redis).

Celery notes (see `backend/worker/celery_app.py`): separate **`ingest`** / **`wiki`** queues, late acks, prefetch 1, soft/hard time limits, ingestion rate limit **30/min**, `worker_max_tasks_per_child` to limit memory growth.

## Rate limiting

- **Chat**: `daily_query_limit` (default **20**) per user per day; enforced in the WebSocket handler via Redis.
- **nginx**: per-IP limits on `/api/` and connection limits on `/ws/` (see `nginx/nginx.conf`).

## Stale detection

On `GET /api/repos/{id}`, a background task compares the latest GitHub commit SHA with `last_commit_sha`. If they differ, the repo is marked **`stale`** so the UI can prompt a re-index.

## Development (without Docker)

**Backend** — from `backend/`, with a real Postgres, Redis, and RabbitMQ:

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql://...
export REDIS_URL=redis://:password@localhost:6379
export RABBITMQ_URL=amqp://user:password@localhost:5672//
export SECRET_KEY=... FERNET_KEY=... ANTHROPIC_API_KEY=... GITHUB_CLIENT_ID=... GITHUB_CLIENT_SECRET=...
uvicorn api.main:app --reload --port 8001
```

**Celery worker** — same env:

```bash
cd backend
celery -A worker.celery_app worker --queues=ingest,wiki --concurrency=2 --loglevel=info
```

**Frontend**:

```bash
cd frontend
npm install
npm run dev
```

## Optional

- **RLS policy checks**: `python scripts/verify_rls_policies.py` (from repo root) against your DB — see `backend/db/RLS.md`.
