from celery import Celery
from core.config import settings

celery_app = Celery(
    "researchwiki",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,

    # Task time limits — prevents hung workers on large repos or slow API calls
    task_soft_time_limit=600,       # 10 min — SIGTERM sent, task can clean up
    task_time_limit=660,            # 11 min — SIGKILL if still running
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks (prevents memory leaks)

    # Separate queues — wiki generation never blocks ingestion
    task_routes={
        "worker.tasks.ingest_repo": {"queue": "ingest"},
        "worker.tasks.generate_wiki_page_task": {"queue": "wiki"},
    },

    # Rate limit ingestion to prevent a single user from saturating workers
    task_annotations={
        "worker.tasks.ingest_repo": {"rate_limit": "30/m"},
    },
)
