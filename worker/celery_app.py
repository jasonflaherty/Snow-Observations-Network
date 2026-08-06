from celery import Celery
from celery.schedules import crontab

from son_core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "son",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["worker.tasks"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "ingest-all-hourly": {
            "task": "worker.tasks.ingest_all_task",
            "schedule": crontab(minute=5),
        }
    },
)
