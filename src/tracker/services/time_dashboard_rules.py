from __future__ import annotations

from datetime import datetime

from ..models import TimeBucket, TimeBucketAssignment, TimeLayout, UserItem
from .time_dashboard import (
    build_bucket_option_list,
    build_bucket_paths,
    build_chart_entries,
    load_item_durations,
)
from .time_windows import build_time_windows


def build_dashboard_context_for_user(
    *,
    user,
    layout_id: str | None,
    bucket_id: int | None,
    show_zero_time: bool,
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

    daily_contexts: list[dict[str, object]] = []
    rolling_contexts: list[dict[str, object]] = []
    all_time_context: dict[str, object] = {"label": "All time", "entries": []}
    all_time_assignments = {
        "unassigned_items": [],
        "ignored_items": [],
        "selected_bucket": None,
    }
    selector_windows = []

    if layout:
        time_windows = build_time_windows()
        daily_windows = [w for w in time_windows if w.group == "daily"]
        rolling_windows = [w for w in time_windows if w.group == "rolling"]
        all_time_window = next((w for w in time_windows if w.group == "all_time"), None)
        selector_windows = [{"key": w.key, "label": w.label} for w in time_windows]

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
                top_n=None,
                include_zero_time=include_zero_time,
            )
            chart["label"] = label
            return chart

        for window in daily_windows:
            daily_contexts.append(
                period_context(
                    window.start,
                    window.end,
                    window.label,
                    include_zero_time=show_zero_time,
                )
            )

        for window in rolling_windows:
            rolling_contexts.append(
                period_context(
                    window.start,
                    window.end,
                    window.label,
                    include_zero_time=show_zero_time,
                )
            )

        if all_time_window is not None:
            all_time_context = period_context(
                all_time_window.start,
                all_time_window.end,
                all_time_window.label,
                include_zero_time=show_zero_time,
            )
            all_time_durations = load_item_durations(
                user, all_time_window.start, all_time_window.end
            )
        else:
            all_time_durations = load_item_durations(user, None, None)

        all_time_assignments = build_chart_entries(
            layout=layout,
            buckets=buckets,
            assignments=assignments,
            item_durations=all_time_durations,
            user_items=user_items,
            bucket_id=None,
            top_n=None,
            include_zero_time=show_zero_time,
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
        "daily_contexts": daily_contexts,
        "rolling_contexts": rolling_contexts,
        "all_time_context": all_time_context,
        "unassigned_items": all_time_assignments["unassigned_items"],
        "ignored_items": all_time_assignments["ignored_items"],
        "selected_bucket": selected_bucket,
        "breadcrumb_buckets": breadcrumb_buckets,
        "selector_windows": selector_windows,
        "show_zero_time": show_zero_time,
    }
