import os
from celery import Celery

app = Celery("greenplan", broker=os.environ["CELERY_BROKER_URL"])
app.conf.update(
    task_default_queue="oda",
    task_routes={
        "tasks.libredwg_probe": {"queue": "libredwg"},
        "tasks.intake_libredwg_probe": {"queue": "libredwg"},
    },
)

import tasks  # noqa: E402,F401
