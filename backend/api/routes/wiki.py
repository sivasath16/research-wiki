import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
import redis as redis_lib

from api.middleware.auth_middleware import get_current_user
from db.models import Chunk, Repo, User, WikiPage, WikiGenerationStatus
from db.session import get_db
from core.config import settings
from worker.tasks import generate_wiki_page_task

router = APIRouter()

_redis: redis_lib.Redis | None = None

def _get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _redis

_DISPATCH_TTL = 120  # seconds — don't re-dispatch while a task is in-flight

def _dispatch_wiki_task(repo_id: int, path: str):
    """Dispatch wiki generation task, guarded by a Redis key to prevent duplicate dispatches."""
    key = f"wiki_dispatched:{repo_id}:{path}"
    r = _get_redis()
    if not r.set(key, "1", ex=_DISPATCH_TTL, nx=True):
        return  # task already dispatched and likely in-flight
    generate_wiki_page_task.apply_async(args=[repo_id, path], queue="wiki")


@router.get("/{repo_id}/pages")
def list_wiki_pages(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all available wiki pages for a repo (paths only)."""
    repo = db.query(Repo).filter(Repo.id == repo_id, Repo.user_id == current_user.id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    pages = db.query(WikiPage).filter(WikiPage.repo_id == repo_id).all()

    # Use precomputed file_tree from Repo — O(1) vs O(chunks) scan
    file_tree: list[str] = repo.file_tree or []

    all_dirs: set[str] = set()
    for fp in file_tree:
        parts = fp.split("/")
        for i in range(1, len(parts)):
            all_dirs.add("/".join(parts[:i]))

    existing_paths = {p.path for p in pages}
    available_dirs = sorted(all_dirs - existing_paths)

    return {
        "pages": [
            {
                "path": p.path,
                "title": p.title,
                "generated_at": p.generated_at.isoformat() if p.generated_at else None,
                "has_content": p.content_md is not None,
            }
            for p in pages
        ],
        "available_dirs": available_dirs,
    }


@router.get("/{repo_id}/pages/{page_path:path}")
def get_wiki_page(
    repo_id: int,
    page_path: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get (or trigger async generation of) a wiki page."""
    repo = db.query(Repo).filter(Repo.id == repo_id, Repo.user_id == current_user.id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    if repo.index_status not in ("ready", "stale"):
        raise HTTPException(status_code=400, detail="Repo is not ready yet")

    path = page_path.strip("/") or "overview"

    page = db.query(WikiPage).filter(WikiPage.repo_id == repo_id, WikiPage.path == path).first()

    if page and page.generation_status == WikiGenerationStatus.ready:
        return _page_dict(page)

    if not page:
        # Look up semantic title from wiki_structure (set during ingest)
        page_title = None
        if repo.wiki_structure:
            match = next((p for p in repo.wiki_structure if p.get("dir_path") == path), None)
            if match:
                page_title = match.get("title")
        if not page_title:
            if path == "overview":
                page_title = f"{repo.owner}/{repo.name} — Overview"
            else:
                page_title = path.split("/")[-1].replace("_", " ").title()

        # Upsert to avoid IntegrityError on concurrent requests for the same page
        stmt = pg_insert(WikiPage).values(
            repo_id=repo_id,
            path=path,
            title=page_title,
            content_md=None,
            mermaid_diagram=None,
            generated_at=None,
            generation_status=WikiGenerationStatus.pending.value,
        ).on_conflict_do_nothing(index_elements=["repo_id", "path"])
        db.execute(stmt)
        db.commit()
        page = db.query(WikiPage).filter(WikiPage.repo_id == repo_id, WikiPage.path == path).first()
        _dispatch_wiki_task(repo_id, path)
    elif page.generation_status == WikiGenerationStatus.failed:
        page.generation_status = WikiGenerationStatus.pending
        db.commit()
        _dispatch_wiki_task(repo_id, path)
    elif page.generation_status == WikiGenerationStatus.pending:
        _dispatch_wiki_task(repo_id, path)

    return _page_dict(page)


# Tags that can execute scripts or load external resources — strip from AI output
_DANGEROUS = re.compile(
    r"<(script|iframe|object|embed|form|input|button|link|meta|style)\b[^>]*>.*?</\1>"
    r"|<(script|iframe|object|embed|form|input|button|link|meta|style)\b[^>]*/?>",
    re.IGNORECASE | re.DOTALL,
)
_DANGEROUS_ATTRS = re.compile(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)
_JS_HREF = re.compile(r'href\s*=\s*["\']javascript:[^"\']*["\']', re.IGNORECASE)


def _sanitize(text: str | None) -> str | None:
    if not text:
        return text
    text = _DANGEROUS.sub("", text)
    text = _DANGEROUS_ATTRS.sub("", text)
    text = _JS_HREF.sub('href="#"', text)
    return text


def _page_dict(page: WikiPage) -> dict:
    return {
        "id": page.id,
        "repo_id": page.repo_id,
        "path": page.path,
        "title": page.title,
        "content_md": _sanitize(page.content_md),
        "mermaid_diagram": _sanitize(page.mermaid_diagram),
        "generated_at": page.generated_at.isoformat() if page.generated_at else None,
        "generation_status": page.generation_status,
        "generating": page.generation_status in (WikiGenerationStatus.pending, WikiGenerationStatus.running),
    }
