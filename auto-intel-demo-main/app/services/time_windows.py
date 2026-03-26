from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class BriefingWindow:
    edition_date: date
    timezone: str
    cutoff_hour: int
    cutoff_minute: int
    start_at: datetime
    end_at: datetime
    start_local: datetime
    end_local: datetime

    @property
    def cutoff_label(self) -> str:
        return f"{self.cutoff_hour:02d}:{self.cutoff_minute:02d}"

    @property
    def label(self) -> str:
        return f"{self.start_local.strftime('%m-%d %H:%M')} -> {self.end_local.strftime('%m-%d %H:%M')}"

    @property
    def duration_hours(self) -> int:
        return int((self.end_at - self.start_at).total_seconds() // 3600)


def shanghai_now() -> datetime:
    return datetime.now(timezone.utc).astimezone(SHANGHAI_TZ)


def shanghai_today() -> date:
    return shanghai_now().date()


def shanghai_day_bounds(target_date: date | None = None) -> tuple[datetime, datetime]:
    day = target_date or shanghai_today()
    start_local = datetime.combine(day, time.min, tzinfo=SHANGHAI_TZ)
    end_local = datetime.combine(day, time.max, tzinfo=SHANGHAI_TZ)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _briefing_zone() -> ZoneInfo:
    settings = get_settings()
    return ZoneInfo(settings.scheduler_timezone or "Asia/Shanghai")


def briefing_now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_briefing_zone())


def current_briefing_edition_date(now: datetime | None = None) -> date:
    settings = get_settings()
    local_now = briefing_now(now)
    cutoff_today = local_now.replace(
        hour=settings.scheduler_cron_hour,
        minute=settings.scheduler_cron_minute,
        second=0,
        microsecond=0,
    )
    if local_now >= cutoff_today:
        return local_now.date()
    return (local_now - timedelta(days=1)).date()


def briefing_window(target_date: date | None = None) -> BriefingWindow:
    settings = get_settings()
    zone = _briefing_zone()
    edition_date = target_date or current_briefing_edition_date()
    end_local = datetime.combine(
        edition_date,
        time(hour=settings.scheduler_cron_hour, minute=settings.scheduler_cron_minute),
        tzinfo=zone,
    )
    start_local = end_local - timedelta(days=1)
    return BriefingWindow(
        edition_date=edition_date,
        timezone=settings.scheduler_timezone or "Asia/Shanghai",
        cutoff_hour=settings.scheduler_cron_hour,
        cutoff_minute=settings.scheduler_cron_minute,
        start_at=start_local.astimezone(timezone.utc),
        end_at=end_local.astimezone(timezone.utc),
        start_local=start_local,
        end_local=end_local,
    )


def followup_window(target_date: date | None = None, *, days: int = 7) -> tuple[datetime, datetime]:
    window = briefing_window(target_date)
    start_local = window.start_local - timedelta(days=days)
    return start_local.astimezone(timezone.utc), window.start_at


def to_shanghai(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(SHANGHAI_TZ)


def format_shanghai(value: datetime | None, fallback: str = "-") -> str:
    local_value = to_shanghai(value)
    if local_value is None:
        return fallback
    return local_value.strftime("%Y-%m-%d %H:%M")
