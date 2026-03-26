from __future__ import annotations

import time

from app.config import get_settings
from app.db import init_db
from app.scheduler import start_scheduler, stop_scheduler


def main() -> None:
    init_db()
    settings = get_settings()
    start_scheduler(force=True)
    print(
        {
            "status": "scheduler_started",
            "trigger": settings.scheduler_trigger,
            "timezone": settings.scheduler_timezone,
            "cron_hour": settings.scheduler_cron_hour,
            "cron_minute": settings.scheduler_cron_minute,
            "interval_minutes": settings.scheduler_interval_minutes,
        }
    )
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        stop_scheduler()
        print({"status": "scheduler_stopped"})


if __name__ == "__main__":
    main()
