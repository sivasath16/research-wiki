from celery import Celery
from core.config import settings

celery_app = Celery(
    "researchwiki",
    broker=settings.rabbitmq_url,   # RabbitMQ — durable queues, per-message acks
    backend=settings.redis_url,     # Redis — fast result/state storage
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

    # Per-task time limits below. (Global limits would kill multi-hour ingests.)
    worker_max_tasks_per_child=50,  # prefork only; ignored for --pool=solo

    # Separate queues — wiki generation never blocks ingestion
    task_routes={
        "worker.tasks.ingest_repo": {"queue": "ingest"},
        "worker.tasks.generate_wiki_page_task": {"queue": "wiki"},
    },

    # Per-task limits: ingest can run for hours (embeddings); wiki pages stay bounded.
    task_annotations={
        "worker.tasks.ingest_repo": {
            "rate_limit": "30/m",
            "soft_time_limit": 8 * 3600,
            "time_limit": 8 * 3600 + 300,
        },
        "worker.tasks.generate_wiki_page_task": {
            "soft_time_limit": 600,
            "time_limit": 660,
        },
    },
)
