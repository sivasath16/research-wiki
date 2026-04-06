import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from api.middleware.auth_middleware import get_current_user
from db.models import Job, User
from db.rls_context import user_rls
from db.session import get_db, SessionLocal

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/{job_id}")
def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_dict(job)


@router.get("/{job_id}/stream")
async def stream_job_progress(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    SSE endpoint — pushes job progress every second until completed/failed.
    Replaces frontend polling entirely.
    """
    user_id = current_user.id

    async def event_generator():
        with user_rls(user_id):
            db = SessionLocal()
            try:
                while True:
                    job = db.query(Job).filter(
                        Job.id == job_id,
                        Job.user_id == user_id,
                    ).first()

                    if not job:
                        yield {"data": json.dumps({"error": "Job not found"})}
                        break

                    db.refresh(job)  # Ensure we get latest state
                    payload = _job_dict(job)
                    yield {"data": json.dumps(payload)}

                    if job.status in ("completed", "failed"):
                        break

                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass  # Client disconnected
            finally:
                db.close()

    return EventSourceResponse(event_generator())


def _job_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "repo_id": job.repo_id,
        "status": job.status,
        "progress_step": job.progress_step,
        "progress_pct": job.progress_pct,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }
