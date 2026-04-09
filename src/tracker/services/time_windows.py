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


def _calendar_window(today: date, *, days: int) -> tuple[datetime, datetime]:
    start_day = today - timedelta(days=days - 1)
    start, _ = day_range(start_day)
    _, end = day_range(today)
    return start, end


def build_time_windows(now: datetime | None = None) -> list[TimeWindow]:
    now = now or timezone.now()
    today = timezone.localdate(now)
    yesterday = today - timedelta(days=1)

    today_start, today_end = day_range(today)
    yesterday_start, yesterday_end = day_range(yesterday)

    last_7_start, last_7_end = _calendar_window(today, days=7)
    last_14_start, last_14_end = _calendar_window(today, days=14)
    last_21_start, last_21_end = _calendar_window(today, days=21)
    last_30_start, last_30_end = _calendar_window(today, days=30)
    last_60_start, last_60_end = _calendar_window(today, days=60)
    last_90_start, last_90_end = _calendar_window(today, days=90)
    last_365_start, last_365_end = _calendar_window(today, days=365)

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
            key="last_7",
            label="Last 7 days",
            start=last_7_start,
            end=last_7_end,
            group="rolling",
        ),
        TimeWindow(
            key="last_14",
            label="Last 14 days",
            start=last_14_start,
            end=last_14_end,
            group="rolling",
        ),
        TimeWindow(
            key="last_21",
            label="Last 21 days",
            start=last_21_start,
            end=last_21_end,
            group="rolling",
        ),
        TimeWindow(
            key="last_30",
            label="Last 30 days",
            start=last_30_start,
            end=last_30_end,
            group="rolling",
        ),
        TimeWindow(
            key="last_60",
            label="Last 60 days",
            start=last_60_start,
            end=last_60_end,
            group="rolling",
        ),
        TimeWindow(
            key="last_90",
            label="Last 90 days",
            start=last_90_start,
            end=last_90_end,
            group="rolling",
        ),
        TimeWindow(
            key="last_365",
            label="Last 365 days",
            start=last_365_start,
            end=last_365_end,
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


def build_picker_windows() -> list[TimeWindow]:
    return [
        window
        for window in build_time_windows()
        if window.key in {
            "last_7",
            "last_14",
            "last_21",
            "last_30",
            "last_60",
            "last_90",
            "last_365",
            "all_time",
        }
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
