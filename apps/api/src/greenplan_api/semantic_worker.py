from __future__ import annotations

import os
from uuid import UUID

from celery import Celery

from .semantic_jobs import execute_semantic_suggestion_job


celery = Celery(
    "greenplan-semantic",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
)
celery.conf.task_default_queue = "semantic"


@celery.task(name="greenplan.semantic.suggest_layers")
def suggest_layers(job_id: str) -> None:
    execute_semantic_suggestion_job(
        os.environ["GREENPLAN_DATABASE_URL"], os.getenv("LAYA_URL", ""), UUID(job_id),
    )
