"""
RAG pipeline:
  condense query → embed → pgvector search → cross-encoder rerank → stream via Claude Sonnet.

Improvements over v1:
- Cross-encoder reranking (ms-marco-MiniLM-L-6-v2) replaces LLM reranking
- Query condensation using conversation history
- Semantic cache (cosine similarity on query embeddings)
- Chunk type filtering based on query intent
- Multi-repo retrieval (cross-repo dependency support)
"""
import json
import time
from typing import AsyncGenerator, List

import anthropic
import numpy as np
import redis as redis_lib
from sentence_transformers import CrossEncoder
from sqlalchemy import text
from sqlalchemy.orm import Session

from worker.embedder import embed_query
from core.config import settings

_anthropic_client: anthropic.Anthropic | None = None
_redis: redis_lib.Redis | None = None
_reranker: CrossEncoder | None = None


def _get_anthropic() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def _get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(settings.reranker_model)
    return _reranker


# ── Query intent classification ───────────────────────────────────────────────

_USAGE_KEYWORDS = {"how to", "how do", "example", "usage", "use ", "configure", "setup", "tutorial", "guide", "quickstart"}
_IMPL_KEYWORDS = {
    "how does", "how is", "how are", "how was", "implementation", "internals",
    "under the hood", "algorithm", "source", "works", "happening", "implemented",
    "structured", "built", "logic", "flow", "process", "mechanism",
}


def classify_query_intent(query: str) -> str:
    """Returns 'usage', 'implementation', or 'general'."""
    q = query.lower()
    if any(k in q for k in _IMPL_KEYWORDS):
        return "implementation"
    if any(k in q for k in _USAGE_KEYWORDS):
        return "usage"
    return "general"


def _chunk_types_for_intent(intent: str) -> List[str] | None:
    if intent == "usage":
        return ["doc", "module"]
    if intent == "implementation":
        return ["function", "class", "module"]
    # general: prefer code chunks but don't exclude docs entirely
    return ["function", "class", "module", "block"]


# ── Query condensation ────────────────────────────────────────────────────────

def condense_query(query: str, history: List[dict]) -> str:
    """
    Rewrite a follow-up query as a standalone search query using conversation history.
    Only called when history exists — avoids unnecessary Haiku call on first message.
    """
    if not history:
        return query

    client = _get_anthropic()
    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content'][:300]}"
        for m in history[-4:]
    )

    try:
        response = client.messages.create(
            model=settings.haiku_model,
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": (
                    f"Conversation so far:\n{history_text}\n\n"
                    f'Rewrite this follow-up as a self-contained search query (no pronouns, full context):\n"{query}"\n\n'
                    "Output ONLY the rewritten query."
                ),
            }],
        )
        return response.content[0].text.strip() or query
    except Exception:
        return query


# ── Semantic cache ────────────────────────────────────────────────────────────

_SEM_CACHE_TTL = 3600          # 1 hour
_SEM_CACHE_THRESHOLD = 0.95    # cosine similarity threshold
_SEM_CACHE_MAX_ENTRIES = 100   # max entries per repo to scan


def _sem_cache_key(repo_id: int) -> str:
    # All entries for a repo stored in one Redis Hash — single HGETALL vs N GET calls
    return f"sem_cache_v2:{repo_id}"


def check_semantic_cache(query_embedding: List[float], repo_id: int) -> str | None:
    r = _get_redis()
    entries = r.hgetall(_sem_cache_key(repo_id))
    if not entries:
        return None

    q_vec = np.array(query_embedding, dtype=np.float32)
    best_score = 0.0
    best_response = None

    for raw in list(entries.values())[:_SEM_CACHE_MAX_ENTRIES]:
        try:
            data = json.loads(raw)
            cached_vec = np.array(data["embedding"], dtype=np.float32)
            score = float(np.dot(q_vec, cached_vec))  # embeddings are L2-normalized
            if score > best_score:
                best_score = score
                best_response = data["response"]
        except Exception:
            continue

    if best_score >= _SEM_CACHE_THRESHOLD and best_response:
        return best_response
    return None


def clear_semantic_cache(repo_id: int):
    """Drop all cached responses for a repo — called on full reindex."""
    _get_redis().delete(_sem_cache_key(repo_id))


def store_semantic_cache(query_embedding: List[float], response: str, repo_id: int):
    r = _get_redis()
    cache_key = _sem_cache_key(repo_id)
    field = str(int(time.time() * 1000))
    r.hset(cache_key, field, json.dumps({
        "embedding": query_embedding,
        "response": response,
    }))
    r.expire(cache_key, _SEM_CACHE_TTL)

    # Evict oldest entries beyond the cap
    all_fields = r.hkeys(cache_key)
    if len(all_fields) > _SEM_CACHE_MAX_ENTRIES:
        oldest = sorted(all_fields)[: len(all_fields) - _SEM_CACHE_MAX_ENTRIES]
        r.hdel(cache_key, *oldest)


# ── Retrieval ─────────────────────────────────────────────────────────────────

def retrieve_chunks(
    db: Session,
    repo_ids: List[int] | int,
    query: str,
    top_k: int = 20,
    chunk_types: List[str] | None = None,
    query_embedding: List[float] | None = None,
) -> List[dict]:
    """
    Embed query and fetch top_k chunks via pgvector ANN search.
    Supports multiple repo_ids for cross-repo retrieval.
    Pass query_embedding to skip re-embedding if already computed.
    """
    if isinstance(repo_ids, int):
        repo_ids = [repo_ids]

    embedding = query_embedding if query_embedding is not None else embed_query(query)
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

    type_filter = ""
    params: dict = {
        "repo_ids": repo_ids,
        "emb": embedding_str,
        "limit": top_k,
    }

    if chunk_types:
        type_filter = "AND chunk_type = ANY(:chunk_types)"
        params["chunk_types"] = chunk_types

    rows = db.execute(
        text(f"""
            SELECT id, repo_id, file_path, content, chunk_type, name,
                   start_line, end_line, language,
                   1 - (embedding <=> CAST(:emb AS vector)) AS score
            FROM chunks
            WHERE repo_id = ANY(:repo_ids)
            {type_filter}
            ORDER BY embedding <=> CAST(:emb AS vector)
            LIMIT :limit
        """),
        params,
    ).fetchall()

    return [
        {
            "id": r.id,
            "repo_id": r.repo_id,
            "file_path": r.file_path,
            "content": r.content,
            "chunk_type": r.chunk_type,
            "name": r.name,
            "start_line": r.start_line,
            "end_line": r.end_line,
            "language": r.language,
            "score": float(r.score),
            "_query_embedding": embedding,  # carry through to avoid re-embedding
        }
        for r in rows
    ]


def rerank_chunks(query: str, chunks: List[dict], top_k: int = 5) -> List[dict]:
    """
    Rerank using cross-encoder/ms-marco-MiniLM-L-6-v2.
    Pure local inference — no LLM call, ~10x lower latency than Haiku reranking.
    """
    if len(chunks) <= top_k:
        return chunks

    reranker = _get_reranker()
    pairs = [(query, c["content"][:512]) for c in chunks]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    return [c for _, c in ranked[:top_k]]


def build_context(chunks: List[dict]) -> str:
    parts = []
    for c in chunks:
        header = f"### {c['file_path']}"
        if c.get("name"):
            header += f" — `{c['name']}`"
        header += f" (lines {c.get('start_line', '?')}-{c.get('end_line', '?')})"
        parts.append(f"{header}\n```{c.get('language', '')}\n{c['content']}\n```")
    return "\n\n".join(parts)


async def stream_answer(
    query: str,
    repo_owner: str,
    repo_name: str,
    chunks: List[dict],
    repo_id: int = 0,
    history: List[dict] | None = None,
    query_embedding: List[float] | None = None,
    wiki_pages: List[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """Stream Claude Sonnet answer token by token with semantic caching."""
    client = _get_anthropic()

    if query_embedding is None:
        query_embedding = embed_query(query)

    if not history:
        cached = check_semantic_cache(query_embedding, repo_id)
        if cached:
            yield cached
            return

    # Build context: wiki articles first (high-level), then code chunks (low-level)
    context_parts = []
    if wiki_pages:
        wiki_context = "\n\n".join(
            f"## Wiki: {p['title']}\n{p['content_md']}"
            for p in wiki_pages
        )
        context_parts.append(f"### High-level documentation\n{wiki_context}")
    context_parts.append(f"### Code context\n{build_context(chunks)}")
    context = "\n\n---\n\n".join(context_parts)

    system_prompt = (
        f"You are an expert code assistant helping researchers understand "
        f"the `{repo_owner}/{repo_name}` codebase.\n\n"
        "You have been given high-level wiki documentation AND raw code snippets as context. "
        "Use both to answer accurately. When referencing code: mention the file path and "
        "function/class name, use inline code formatting, be concise but thorough.\n"
        "If the answer is not clear from the context, say so honestly."
    )

    user_message = f"Context:\n{context}\n\nQuestion: {query}"
    messages = list(history or []) + [{"role": "user", "content": user_message}]

    full_response = ""
    with client.messages.stream(
        model=settings.sonnet_model,
        max_tokens=2000,
        system=system_prompt,
        messages=messages,
    ) as stream:
        for token in stream.text_stream:
            full_response += token
            yield token

    # Cache first-turn responses for semantic reuse
    if not history and full_response:
        store_semantic_cache(query_embedding, full_response, repo_id)


def get_relevant_wiki_pages(db: Session, repo_id: int, query: str, top_k: int = 2) -> List[dict]:
    """
    Find wiki pages whose title or content is most relevant to the query.
    Returns a list of {"title": ..., "content_md": ...} dicts.
    Used to provide high-level context in chat answers.
    """
    from sqlalchemy import text as sa_text
    try:
        rows = db.execute(
            sa_text(
                "SELECT title, content_md FROM wiki_pages "
                "WHERE repo_id = :repo_id AND generation_status = 'ready' AND content_md IS NOT NULL "
                "LIMIT 20"
            ),
            {"repo_id": repo_id},
        ).fetchall()
    except Exception:
        return []

    if not rows:
        return []

    # Score each page by keyword overlap with the query (simple, no extra embed call)
    q_words = set(query.lower().split())
    scored = []
    for row in rows:
        title_words = set(row.title.lower().split())
        overlap = len(q_words & title_words)
        # Also check content snippet
        snippet = (row.content_md or "")[:500].lower()
        content_hits = sum(1 for w in q_words if w in snippet)
        scored.append((overlap * 3 + content_hits, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [row for score, row in scored[:top_k] if score > 0]

    return [
        {"title": row.title, "content_md": (row.content_md or "")[:1500]}
        for row in top
    ]


def get_source_references(chunks: List[dict]) -> List[dict]:
    seen = set()
    refs = []
    for c in chunks:
        key = (c["file_path"], c.get("name"))
        if key not in seen:
            seen.add(key)
            refs.append({
                "file_path": c["file_path"],
                "name": c.get("name"),
                "start_line": c.get("start_line"),
                "end_line": c.get("end_line"),
                "language": c.get("language"),
                "repo_id": c.get("repo_id"),
            })
    return refs
