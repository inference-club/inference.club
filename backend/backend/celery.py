"""Celery application for the inference.club backend.

Celery is the *execution* layer for async jobs (PRD 10); Postgres stays the
source of truth. The worker runs jobs, and Celery beat fires the dispatcher
tick that claims queued jobs and assigns them to providers with free capacity.

Async is opt-in and degrades safely: if no broker is configured (no REDIS_URL),
``settings.ASYNC_ENABLED`` is False, the beat schedule is empty, and the API
rejects async submissions with a clear 503 — synchronous inference is wholly
unaffected, with or without Celery running.
"""
import os

from celery import Celery
from celery.schedules import crontab  # noqa: F401  (available for cron workflows later)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

app = Celery("inference_club")

# All CELERY_* settings come from Django settings.
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):  # pragma: no cover - smoke helper
    print(f"Request: {self.request!r}")
