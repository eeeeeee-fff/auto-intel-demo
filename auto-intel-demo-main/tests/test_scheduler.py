from app.config import Settings
from app.scheduler import build_scheduler_job_kwargs


def test_build_scheduler_job_kwargs_for_cron() -> None:
    settings = Settings(
        scheduler_enabled=True,
        scheduler_trigger="cron",
        scheduler_timezone="Asia/Shanghai",
        scheduler_cron_hour=5,
        scheduler_cron_minute=0,
    )

    kwargs = build_scheduler_job_kwargs(settings)

    assert kwargs == {"trigger": "cron", "hour": 5, "minute": 0}


def test_build_scheduler_job_kwargs_for_interval() -> None:
    settings = Settings(
        scheduler_enabled=True,
        scheduler_trigger="interval",
        scheduler_interval_minutes=30,
    )

    kwargs = build_scheduler_job_kwargs(settings)

    assert kwargs == {"trigger": "interval", "minutes": 30}
