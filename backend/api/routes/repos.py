import re
import uuid
from datetime import datetime

import httpx
import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.middleware.auth_middleware import get_current_user
from core.config import settings
from core.security import decrypt_token
from db.models import IndexStatus, Job, JobStatus, Repo, User
from db.session import get_db
from worker.tasks import ingest_repo

router = APIRouter()

_redis: redis_lib.Redis | None = None


def get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _redis


class IngestRequest(BaseModel):
    url: str


def _parse_repo_url(url: str) -> tuple[str, str]:
    pattern = r"github\.com[/:]([^/]+)/([^/\.]+?)(?:\.git)?$"
    m = re.search(pattern, url.strip())
    if not m:
        raise HTTPException(status_code=400, detail="Invalid GitHub repo URL")
    return m.group(1), m.group(2)


async def _get_latest_sha(owner: str, name: str, token: str) -> str | None:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{name}/commits/HEAD",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("sha")
    return None


async def _get_repo_meta(owner: str, name: str, token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/repos/{owner}/{name}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    return {}


async def _check_staleness(repo_id: int, owner: str, name: str, token: str, known_sha: str | None):
    """Background task: check if repo has new commits, mark stale if so."""
    from db.session import SessionLocal
    db = SessionLocal()
    try:
        latest_sha = await _get_latest_sha(owner, name, token)
        if latest_sha and known_sha and latest_sha != known_sha:
            repo = db.query(Repo).filter(Repo.id == repo_id).first()
            if repo and repo.index_status == IndexStatus.ready:
                repo.index_status = IndexStatus.stale
                repo.updated_at = datetime.utcnow()
                db.commit()
    except Exception:
        pass
    finally:
        db.close()


@router.post("/ingest")
async def ingest(
    body: IngestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    owner, name = _parse_repo_url(body.url)
    github_token = decrypt_token(current_user.github_token_encrypted)

    # Fetch repo metadata + latest SHA
    meta = await _get_repo_meta(owner, name, github_token)
    if not meta:
        raise HTTPException(status_code=404, detail="GitHub repo not found or no access")

    # Repo size guard — reject very large repos before cloning
    repo_size_kb = meta.get("size", 0)
    if repo_size_kb > settings.max_repo_size_kb:
        raise HTTPException(
            status_code=400,
            detail=f"Repository too large ({repo_size_kb // 1024}MB). Max allowed: {settings.max_repo_size_kb // 1024}MB.",
        )

    # Per-user concurrent job limit
    active_jobs = db.query(Job).filter(
        Job.user_id == current_user.id,
        Job.status.in_([JobStatus.pending, JobStatus.running]),
    ).count()
    if active_jobs >= settings.max_concurrent_jobs:
        raise HTTPException(
            status_code=429,
            detail=f"Too many active indexing jobs (max {settings.max_concurrent_jobs}). Wait for one to finish.",
        )

    latest_sha = await _get_latest_sha(owner, name, github_token)

    # Find or create repo record
    repo = (
        db.query(Repo)
        .filter(Repo.owner == owner, Repo.name == name, Repo.user_id == current_user.id)
        .first()
    )

    if repo:
        # If SHA unchanged and status is ready, skip re-index
        if (
            repo.last_commit_sha
            and repo.last_commit_sha == latest_sha
            and repo.index_status == IndexStatus.ready
        ):
            return {
                "job_id": None,
                "status": "cached",
                "repo_id": repo.id,
                "message": "Already up to date",
            }

        # If currently indexing, return existing job
        lock_key = f"index_lock:{repo.id}"
        if get_redis().exists(lock_key):
            active_job = (
                db.query(Job)
                .filter(Job.repo_id == repo.id, Job.status.in_([JobStatus.pending, JobStatus.running]))
                .order_by(Job.created_at.desc())
                .first()
            )
            return {
                "job_id": active_job.id if active_job else None,
                "status": "indexing",
                "repo_id": repo.id,
            }

        # Update metadata
        repo.description = meta.get("description", repo.description)
        repo.language = meta.get("language", repo.language)
        repo.is_private = meta.get("private", repo.is_private)
        db.commit()
    else:
        repo = Repo(
            owner=owner,
            name=name,
            url=body.url,
            description=meta.get("description"),
            language=meta.get("language"),
            is_private=meta.get("private", False),
            index_status=IndexStatus.pending,
            user_id=current_user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)

    # Acquire Redis lock (TTL = 10min)
    lock_key = f"index_lock:{repo.id}"
    get_redis().set(lock_key, "1", ex=600)

    # Create job record
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        repo_id=repo.id,
        user_id=current_user.id,
        status=JobStatus.pending,
        progress_step="Queued",
        progress_pct=0.0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()

    # Enqueue Celery task — token is decrypted inside the worker, not passed as arg
    ingest_repo.apply_async(
        args=[repo.id, job_id],
        task_id=job_id,
    )

    return {"job_id": job_id, "status": "pending", "repo_id": repo.id}


@router.get("")
def list_repos(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repos = (
        db.query(Repo)
        .filter(Repo.user_id == current_user.id)
        .order_by(Repo.updated_at.desc())
        .all()
    )
    return [_repo_dict(r) for r in repos]


@router.get("/{repo_id}")
async def get_repo(
    repo_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = db.query(Repo).filter(Repo.id == repo_id, Repo.user_id == current_user.id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    # Kick off background staleness check — rate limited to once per hour per repo
    if repo.index_status == IndexStatus.ready and repo.last_commit_sha:
        check_key = f"staleness_checked:{repo.id}"
        if not get_redis().get(check_key):
            get_redis().setex(check_key, 3600, "1")
            github_token = decrypt_token(current_user.github_token_encrypted)
            background_tasks.add_task(
                _check_staleness,
                repo.id,
                repo.owner,
                repo.name,
                github_token,
                repo.last_commit_sha,
            )

    return _repo_dict(repo)


@router.delete("/{repo_id}")
def delete_repo(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = db.query(Repo).filter(Repo.id == repo_id, Repo.user_id == current_user.id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")
    db.delete(repo)
    db.commit()
    get_redis().delete(f"index_lock:{repo_id}")
    return {"status": "deleted"}


def _repo_dict(repo: Repo) -> dict:
    return {
        "id": repo.id,
        "owner": repo.owner,
        "name": repo.name,
        "url": repo.url,
        "description": repo.description,
        "language": repo.language,
        "is_private": repo.is_private,
        "last_commit_sha": repo.last_commit_sha,
        "indexed_at": repo.indexed_at.isoformat() if repo.indexed_at else None,
        "index_status": repo.index_status,
        "chunk_count": repo.chunk_count,
        "file_count": repo.file_count,
        "error_message": repo.error_message,
        "wiki_structure": repo.wiki_structure or [],
        "created_at": repo.created_at.isoformat() if repo.created_at else None,
        "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
    }
