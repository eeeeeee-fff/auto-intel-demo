from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.services.ingestion import bootstrap_sources, run_collection_pipeline


_scheduler: BackgroundScheduler | None = None


def run_scheduled_pipeline() -> None:
    with SessionLocal() as session:
        bootstrap_sources(session)
        run_collection_pipeline(
            session,
            analyze=True,
            translate=True,
            build_digest=True,
            render_report=True,
            trigger_mode="scheduler",
        )


def build_scheduler_job_kwargs(settings: Settings) -> dict:
    if settings.scheduler_trigger == "interval":
        return {
            "trigger": "interval",
            "minutes": settings.scheduler_interval_minutes,
        }
    return {
        "trigger": "cron",
        "hour": settings.scheduler_cron_hour,
        "minute": settings.scheduler_cron_minute,
    }


def start_scheduler(*, force: bool = False) -> None:
    global _scheduler
    settings = get_settings()
    if (not settings.scheduler_enabled and not force) or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)
    _scheduler.add_job(
        run_scheduled_pipeline,
        id="auto-intel-pipeline",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
        **build_scheduler_job_kwargs(settings),
    )
    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
