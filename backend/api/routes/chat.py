"""
WebSocket endpoint for streaming RAG chat.

Cross-repo detection:
  After retrieval, if max chunk score < 0.5, check if the current repo has
  dependencies that match other repos the user has indexed. If so, send a
  dependency_suggestion message and wait for the user to confirm before
  re-retrieving with the extra repos included.
"""
import asyncio
import json
import logging
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator, ValidationError
from sqlalchemy.orm import Session

from api.middleware.auth_middleware import get_current_user
from core.config import settings
from core.rate_limit import consume, get_remaining
from db.models import Repo, User
from db.session import get_db
from rag.retriever import (
    retrieve_chunks, rerank_chunks, stream_answer, get_source_references,
    condense_query, classify_query_intent, _chunk_types_for_intent,
    get_relevant_wiki_pages,
)

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 2000
MAX_HISTORY_TURNS = 6
LOW_CONFIDENCE_THRESHOLD = 0.5


class _WsMessage(BaseModel):
    type: str
    content: str = Field(default="", max_length=MAX_QUERY_LENGTH)
    extra_repo_ids: list[int] = Field(default_factory=list, max_length=10)

    @field_validator("extra_repo_ids")
    @classmethod
    def validate_repo_ids(cls, v: list[int]) -> list[int]:
        if any(rid <= 0 for rid in v):
            raise ValueError("repo IDs must be positive integers")
        return v


async def _ws_send(ws: WebSocket, msg: dict):
    await ws.send_text(json.dumps(msg))


def _find_dependent_repos(db: Session, repo: Repo, user_id: int) -> list[Repo]:
    """
    Return the user's other indexed repos whose name matches a dependency
    declared in the current repo's manifest files.
    """
    if not repo.dependencies:
        return []

    dep_names = {d.lower().replace("-", "_") for d in repo.dependencies}
    other_repos = (
        db.query(Repo)
        .filter(
            Repo.user_id == user_id,
            Repo.id != repo.id,
            Repo.index_status == "ready",
        )
        .all()
    )
    return [
        r for r in other_repos
        if r.name.lower().replace("-", "_") in dep_names
    ]


@router.websocket("/chat/{repo_id}")
async def chat_ws(
    repo_id: int,
    websocket: WebSocket,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    await websocket.accept()

    # Per-connection conversation history
    history: list[dict] = []

    try:
        repo = db.query(Repo).filter(Repo.id == repo_id, Repo.user_id == current_user.id).first()
        if not repo:
            await _ws_send(websocket, {"type": "error", "message": "Repo not found"})
            await websocket.close(code=4003)
            return

        if repo.index_status not in ("ready", "stale"):
            await _ws_send(websocket, {"type": "error", "message": "Repo not ready for chat"})
            await websocket.close(code=4004)
            return

        remaining = get_remaining(current_user.id)
        await _ws_send(websocket, {
            "type": "connected",
            "repo": {"owner": repo.owner, "name": repo.name},
            "rate_limit": {"remaining": remaining, "limit": settings.daily_query_limit},
        })

        # ── Message loop ──────────────────────────────────────────────
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                msg = _WsMessage.model_validate(json.loads(raw))
            except (json.JSONDecodeError, ValidationError):
                await _ws_send(websocket, {"type": "error", "message": "Invalid message"})
                continue

            if msg.type == "ping":
                await _ws_send(websocket, {"type": "pong"})
                continue

            if msg.type != "message":
                continue

            query = msg.content.strip()
            if not query:
                continue

            # Validate extra_repo_ids ownership — drop any IDs not owned by this user
            extra_repo_ids: list[int] = []
            if msg.extra_repo_ids:
                owned = {
                    r[0] for r in db.query(Repo.id).filter(
                        Repo.user_id == current_user.id,
                        Repo.id.in_(msg.extra_repo_ids),
                        Repo.index_status.in_(["ready", "stale"]),
                    ).all()
                }
                extra_repo_ids = [r for r in msg.extra_repo_ids if r in owned]

            # Rate limit
            allowed, remaining = consume(current_user.id)
            if not allowed:
                await _ws_send(websocket, {
                    "type": "rate_limited",
                    "message": "Daily query limit reached. Resets at midnight UTC.",
                    "rate_limit": {"remaining": 0, "limit": settings.daily_query_limit},
                })
                continue

            # ── Query condensation (multi-turn) ───────────────────────
            search_query = query
            if history:
                loop = asyncio.get_event_loop()
                search_query = await loop.run_in_executor(None, condense_query, query, history)

            # ── Chunk type filtering by intent ────────────────────────
            intent = classify_query_intent(search_query)
            chunk_types = _chunk_types_for_intent(intent)

            # ── Retrieval (thread pool — CPU-bound) ───────────────────
            await _ws_send(websocket, {"type": "retrieving"})
            loop = asyncio.get_event_loop()

            all_repo_ids = [repo_id] + [r for r in extra_repo_ids if r != repo_id]
            chunks = await loop.run_in_executor(
                None, retrieve_chunks, db, all_repo_ids, search_query, 20, chunk_types
            )
            # Extract the embedding computed during retrieval to avoid re-embedding for cache
            query_embedding = chunks[0].pop("_query_embedding", None) if chunks else None
            for c in chunks[1:]:
                c.pop("_query_embedding", None)

            # ── Cross-repo dependency suggestion ─────────────────────
            # Only suggest on first try (no extra_repo_ids yet) when confidence is low
            if not extra_repo_ids and chunks:
                max_score = max(c["score"] for c in chunks)
                if max_score < LOW_CONFIDENCE_THRESHOLD:
                    dep_repos = _find_dependent_repos(db, repo, current_user.id)
                    if dep_repos:
                        await _ws_send(websocket, {
                            "type": "dependency_suggestion",
                            "message": (
                                f"I found limited context in `{repo.owner}/{repo.name}`. "
                                f"This repo depends on {'and '.join(f'`{r.owner}/{r.name}`' for r in dep_repos)} "
                                f"which you have indexed. Include {'it' if len(dep_repos) == 1 else 'them'} in this search?"
                            ),
                            "dep_repos": [
                                {"id": r.id, "owner": r.owner, "name": r.name}
                                for r in dep_repos
                            ],
                            "original_query": query,
                        })
                        continue  # Wait for user to respond with extra_repo_ids

            # ── Rerank ────────────────────────────────────────────────
            top_chunks = await loop.run_in_executor(None, rerank_chunks, search_query, chunks, 5)
            sources = get_source_references(top_chunks)

            # ── Augment with wiki context ─────────────────────────────
            wiki_pages = await loop.run_in_executor(
                None, get_relevant_wiki_pages, db, repo_id, search_query
            )

            # ── Stream answer ─────────────────────────────────────────
            await _ws_send(websocket, {"type": "stream_start"})

            full_answer = ""
            try:
                async for token in stream_answer(
                    query,
                    repo.owner,
                    repo.name,
                    top_chunks,
                    db=db,
                    repo_id=repo_id,
                    history=history[-MAX_HISTORY_TURNS * 2:],
                    query_embedding=query_embedding,
                    wiki_pages=wiki_pages,
                    intent=intent,
                ):
                    full_answer += token
                    await _ws_send(websocket, {"type": "token", "content": token})
            except Exception as e:
                logger.error("Streaming error: %s", e)
                await _ws_send(websocket, {"type": "error", "message": "Generation failed"})
                continue

            # Update conversation history
            history.append({"role": "user", "content": query})
            history.append({"role": "assistant", "content": full_answer})

            await _ws_send(websocket, {
                "type": "stream_end",
                "sources": sources,
                "rate_limit": {"remaining": remaining, "limit": settings.daily_query_limit},
            })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("WebSocket error: %s", e)
        try:
            await _ws_send(websocket, {"type": "error", "message": "Server error"})
        except Exception:
            pass
