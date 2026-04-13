"""
scheduler/scheduler.py — APScheduler cron job setup.

Two cron jobs:
  delta_job   — runs every N hours (default */4), extracts incremental updates
  full_load_job — runs once per day at a configured hour (default 01:00 UTC),
                  performs a full-refresh extraction and transformation

Job store: SQLAlchemy (persists across restarts)
Executor:  ThreadPoolExecutor(max_workers=1) per job so only one instance runs at a time
"""
from __future__ import annotations

import signal
import time

import structlog
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from qa_pipeline.settings import PipelineSettings

log = structlog.get_logger(__name__)


def _import_entry_points() -> tuple:
    """Lazy import to avoid circular imports at module load."""
    from qa_pipeline.scripts.run_delta import run_delta_job
    from qa_pipeline.scripts.run_full_load import run_full_load_job
    return run_delta_job, run_full_load_job


def build_scheduler(settings: PipelineSettings) -> BlockingScheduler:
    """
    Construct and configure the BlockingScheduler.
    The caller is responsible for calling scheduler.start().
    """
    job_store_url = settings.scheduler_db_url.get_secret_value()

    jobstores = {
        "default": SQLAlchemyJobStore(url=job_store_url),
    }
    executors = {
        "default": ThreadPoolExecutor(max_workers=1),
    }
    job_defaults = {
        "coalesce":      True,   # merge missed fires into one
        "max_instances": 1,      # mutex — never run two copies simultaneously
        "misfire_grace_time": 300,
    }

    scheduler = BlockingScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone="UTC",
    )

    run_delta_job, run_full_load_job = _import_entry_points()

    # Delta extraction — every N hours (e.g. "*/4")
    scheduler.add_job(
        func=run_delta_job,
        trigger=CronTrigger(hour=settings.extractor_cron_hour, minute=0),
        id="delta_job",
        name="Delta extraction (Jira + Xray incremental)",
        replace_existing=True,
    )
    log.info("scheduler.job_registered", job_id="delta_job", hour=settings.extractor_cron_hour)

    # Full load — once per day
    scheduler.add_job(
        func=run_full_load_job,
        trigger=CronTrigger(hour=settings.full_load_cron_hour, minute=0),
        id="full_load_job",
        name="Full load extraction + transformation",
        replace_existing=True,
    )
    log.info("scheduler.job_registered", job_id="full_load_job", hour=settings.full_load_cron_hour)

    return scheduler


def run_scheduler() -> None:
    """Entry point — build the scheduler and block until SIGTERM/SIGINT."""
    settings = PipelineSettings()
    scheduler = build_scheduler(settings)

    def _shutdown(signum: int, _frame: object) -> None:
        log.info("scheduler.shutdown_requested", signal=signum)
        scheduler.shutdown(wait=True)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    log.info("scheduler.starting")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler.stopped")
