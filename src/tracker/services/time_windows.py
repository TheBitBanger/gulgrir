from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone


@dataclass(frozen=True)
class TimeWindow:
    key: str
    label: str
    start: datetime | None
    end: datetime | None
    group: str


def day_range(day: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    end = start + timedelta(days=1)
    return start, end


def build_time_windows(now: datetime | None = None) -> list[TimeWindow]:
    now = now or timezone.now()
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)

    today_start, today_end = day_range(today)
    yesterday_start, yesterday_end = day_range(yesterday)
    day_before_start, day_before_end = day_range(day_before)

    return [
        TimeWindow(
            key="today",
            label="Today",
            start=today_start,
            end=today_end,
            group="daily",
        ),
        TimeWindow(
            key="yesterday",
            label="Yesterday",
            start=yesterday_start,
            end=yesterday_end,
            group="daily",
        ),
        TimeWindow(
            key="day_before",
            label="Day before",
            start=day_before_start,
            end=day_before_end,
            group="daily",
        ),
        TimeWindow(
            key="last_7",
            label="Last 7 days",
            start=now - timedelta(days=7),
            end=now,
            group="rolling",
        ),
        TimeWindow(
            key="last_30",
            label="Last 30 days",
            start=now - timedelta(days=30),
            end=now,
            group="rolling",
        ),
        TimeWindow(
            key="last_365",
            label="Last 365 days",
            start=now - timedelta(days=365),
            end=now,
            group="rolling",
        ),
        TimeWindow(
            key="all_time",
            label="All time",
            start=None,
            end=None,
            group="all_time",
        ),
    ]


def time_window_choices() -> list[tuple[str, str]]:
    return [(window.key, window.label) for window in build_time_windows()]


def find_time_window(key: str | None) -> TimeWindow | None:
    if not key:
        return None
    for window in build_time_windows():
        if window.key == key:
            return window
    return None
