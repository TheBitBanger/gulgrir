from __future__ import annotations

from datetime import date, datetime

from ..models import TimeBucket, TimeBucketAssignment, TimeLayout, UserItem
from .time_dashboard import (
    build_bucket_option_list,
    build_bucket_paths,
    build_chart_entries,
    load_item_durations,
)
from .time_windows import build_picker_windows, build_time_windows, day_range


def build_dashboard_context_for_user(
    *,
    user,
    layout_id: str | None,
    bucket_id: int | None,
    show_zero_time: bool,
    selected_window_key: str | None = None,
    selected_range_start: date | None = None,
    selected_range_end: date | None = None,
    selected_label: str | None = None,
    expand_depth: int = 3,
) -> dict[str, object]:
    layouts = list(TimeLayout.objects.filter(user=user).order_by("order", "name"))
    layout = None
    if layouts:
        if layout_id:
            layout = next((l for l in layouts if str(l.id) == layout_id), None)
        layout = layout or layouts[0]

    buckets: list[TimeBucket] = []
    assignments: dict[int, TimeBucketAssignment] = {}
    user_items = {
        item.id: item
        for item in UserItem.objects.filter(user=user).select_related("item")
    }

    if layout:
        buckets = list(TimeBucket.objects.filter(layout=layout).select_related("parent"))
        assignments = {
            a.user_item_id: a
            for a in TimeBucketAssignment.objects.filter(layout=layout).select_related(
                "bucket"
            )
        }

    today_context: dict[str, object] = {"label": "Today", "entries": []}
    yesterday_context: dict[str, object] = {"label": "Yesterday", "entries": []}
    selected_context: dict[str, object] = {"label": "All time", "entries": []}
    all_time_assignments = {
        "unassigned_items": [],
        "ignored_items": [],
        "selected_bucket": None,
    }
    selector_windows = []

    if layout:
        time_windows = build_time_windows()
        today_window = next((w for w in time_windows if w.key == "today"), None)
        yesterday_window = next((w for w in time_windows if w.key == "yesterday"), None)
        all_time_window = next((w for w in time_windows if w.group == "all_time"), None)
        selector_windows = [
            {"key": w.key, "label": w.label} for w in build_picker_windows()
        ]

        def period_context(
            start: datetime | None,
            end: datetime | None,
            label: str,
            include_zero_time: bool,
        ):
            durations = load_item_durations(user, start, end)
            chart = build_chart_entries(
                layout=layout,
                buckets=buckets,
                assignments=assignments,
                item_durations=durations,
                user_items=user_items,
                bucket_id=bucket_id,
                include_zero_time=include_zero_time,
                expand_depth=expand_depth,
            )
            chart["label"] = label
            return chart

        if today_window is not None:
            today_context = period_context(
                today_window.start,
                today_window.end,
                today_window.label,
                include_zero_time=show_zero_time,
            )

        if yesterday_window is not None:
            yesterday_context = period_context(
                yesterday_window.start,
                yesterday_window.end,
                yesterday_window.label,
                include_zero_time=show_zero_time,
            )

        if all_time_window is not None:
            all_time_durations = load_item_durations(
                user, all_time_window.start, all_time_window.end
            )
        else:
            all_time_durations = load_item_durations(user, None, None)

        def resolve_selected_window() -> tuple[datetime | None, datetime | None, str]:
            if selected_range_start and selected_range_end:
                start, _ = day_range(selected_range_start)
                _, end = day_range(selected_range_end)
                label = selected_label or "Selected range"
                return start, end, label

            if selected_window_key:
                match = next(
                    (w for w in time_windows if w.key == selected_window_key), None
                )
                if match is not None:
                    return match.start, match.end, selected_label or match.label

            if all_time_window is not None:
                return (
                    all_time_window.start,
                    all_time_window.end,
                    selected_label or all_time_window.label,
                )

            return None, None, selected_label or "All time"

        selected_start, selected_end, selected_label_value = resolve_selected_window()
        selected_context = period_context(
            selected_start,
            selected_end,
            selected_label_value,
            include_zero_time=show_zero_time,
        )

        all_time_assignments = build_chart_entries(
            layout=layout,
            buckets=buckets,
            assignments=assignments,
            item_durations=all_time_durations,
            user_items=user_items,
            bucket_id=None,
            include_zero_time=show_zero_time,
            expand_depth=expand_depth,
        )

    bucket_options = []
    if layout:
        bucket_options = build_bucket_option_list(buckets)

    bucket_by_id = {bucket.id: bucket for bucket in buckets}
    selected_bucket = bucket_by_id.get(bucket_id) if bucket_id else None
    breadcrumb_buckets: list[TimeBucket] = []
    if selected_bucket is not None:
        bucket_paths = build_bucket_paths(buckets)
        path_ids = list(reversed(bucket_paths.get(selected_bucket.id, [])))
        breadcrumb_buckets = [
            bucket_by_id[b_id] for b_id in path_ids if b_id in bucket_by_id
        ]

    return {
        "layouts": layouts,
        "layout": layout,
        "buckets": buckets,
        "bucket_options": bucket_options,
        "today_context": today_context,
        "yesterday_context": yesterday_context,
        "selected_context": selected_context,
        "unassigned_items": all_time_assignments["unassigned_items"],
        "ignored_items": all_time_assignments["ignored_items"],
        "selected_bucket": selected_bucket,
        "breadcrumb_buckets": breadcrumb_buckets,
        "selector_windows": selector_windows,
        "show_zero_time": show_zero_time,
        "expand_depth": expand_depth,
    }
