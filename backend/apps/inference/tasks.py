"""Celery tasks for the async job queue (PRD 10).

Thin wrappers around ``apps.inference.jobs`` / ``apps.inference.workflows``:
- ``dispatch_queued`` — the beat tick that claims due jobs and starts a worker
  task for each, and advances any workflow runs that are ready.
- ``run_job`` — runs one claimed job (the worker).
- ``reap_stuck_jobs`` — reclaims jobs stranded by a dead worker.

All scheduling state lives in Postgres, so a worker/broker restart loses no
work; these tasks just move it forward.
"""
import logging

from celery import shared_task

logger = logging.getLogger("django")


@shared_task(name="apps.inference.tasks.run_job")
def run_job(ir_id):
    from . import jobs
    jobs.run_job(ir_id)


@shared_task(name="apps.inference.tasks.dispatch_queued")
def dispatch_queued(limit=50):
    """Claim queued jobs that can start now and fan a ``run_job`` task out for
    each, then nudge workflow runs whose steps are newly ready."""
    from . import jobs, workflows

    claimed = jobs.dispatch_due_jobs(limit=limit)
    for ir_id in claimed:
        run_job.delay(ir_id)
    workflows.advance_ready_runs()
    return len(claimed)


@shared_task(name="apps.inference.tasks.reap_stuck_jobs")
def reap_stuck_jobs():
    from . import jobs
    return jobs.reap_stuck_jobs()


@shared_task(name="apps.inference.tasks.process_segment")
def process_segment(segment_id):
    """Run the narration pipeline (clean → ASR → trim → grade) on one segment's
    selected take, off the request path (PRD 12 V3)."""
    from . import narration
    from .models import Segment

    seg = Segment.objects.filter(id=segment_id).select_related("episode").first()
    if seg is not None:
        try:
            narration.process_segment(seg)
        except Exception:
            logger.exception("process_segment task failed for segment %s", segment_id)
            seg.status = Segment.STATUS_ERROR
            seg.save(update_fields=["status", "modified_on"])
