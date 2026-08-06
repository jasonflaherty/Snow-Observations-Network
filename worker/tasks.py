from worker.celery_app import celery_app
from worker.ingest import ingest_all


@celery_app.task(name="worker.tasks.ingest_all_task")
def ingest_all_task() -> dict:
    return ingest_all()
