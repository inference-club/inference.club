"""Expose the Celery app so ``@shared_task`` registers against it and a worker
can be started with ``-A backend``. Import is guarded so a missing Celery
install (or import-time error) never breaks the synchronous app."""
try:
    from .celery import app as celery_app

    __all__ = ("celery_app",)
except Exception:  # pragma: no cover - celery optional for sync-only deploys
    celery_app = None
    __all__ = ()
