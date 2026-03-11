from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.db.models import Sum
from django.utils import timezone

from ..models import TimeBucket, TimeBucketAssignment, TimeLayout, UserItem, UserItemHistory


def format_seconds(total_seconds: int) -> str:
    if total_seconds <= 0:
        return "00:00:00"
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def day_range(day: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    end = start + timedelta(days=1)
    return start, end


def load_item_durations(
    user, start: datetime | None, end: datetime | None
) -> dict[int, int]:
    qs = UserItemHistory.objects.filter(
        user_item__user=user,
        event_type=UserItemHistory.Event.REVISITED,
        duration__isnull=False,
        ended_at__isnull=False,
    )
    if start is not None:
        qs = qs.filter(ended_at__gte=start)
    if end is not None:
        qs = qs.filter(ended_at__lt=end)

    durations: dict[int, int] = {}
    for row in qs.values("user_item_id").annotate(total=Sum("duration")):
        total = row["total"]
        if total is None:
            continue
        durations[int(row["user_item_id"])] = int(total.total_seconds())

    return durations


def build_bucket_paths(buckets: list[TimeBucket]) -> dict[int, list[int]]:
    parent_map = {bucket.id: bucket.parent_id for bucket in buckets}
    paths: dict[int, list[int]] = {}

    def path_for(bucket_id: int) -> list[int]:
        if bucket_id in paths:
            return paths[bucket_id]
        path = [bucket_id]
        current = bucket_id
        while parent_map.get(current):
            parent = parent_map[current]
            path.append(parent)
            current = parent
        paths[bucket_id] = path
        return path

    for bucket in buckets:
        if bucket.id is not None:
            path_for(bucket.id)

    return paths


def build_bucket_children_map(
    buckets: list[TimeBucket],
) -> dict[int | None, list[TimeBucket]]:
    bucket_children: dict[int | None, list[TimeBucket]] = defaultdict(list)
    for bucket in buckets:
        bucket_children[bucket.parent_id].append(bucket)
    for child_list in bucket_children.values():
        child_list.sort(key=lambda b: (b.order, b.name.lower()))
    return bucket_children


def build_bucket_descendants(
    buckets: list[TimeBucket],
) -> dict[int, set[int]]:
    bucket_children = build_bucket_children_map(buckets)
    descendants: dict[int, set[int]] = {}

    def collect(bucket_id: int) -> set[int]:
        if bucket_id in descendants:
            return descendants[bucket_id]
        child_ids: set[int] = set()
        for child in bucket_children.get(bucket_id, []):
            if child.id is None:
                continue
            child_ids.add(child.id)
            child_ids.update(collect(child.id))
        descendants[bucket_id] = child_ids
        return child_ids

    for bucket in buckets:
        if bucket.id is None:
            continue
        collect(bucket.id)

    return descendants


def build_chart_entries(
    *,
    layout: TimeLayout,
    buckets: list[TimeBucket],
    assignments: dict[int, TimeBucketAssignment],
    item_durations: dict[int, int],
    user_items: dict[int, UserItem],
    bucket_id: int | None,
    top_n: int,
) -> dict[str, object]:
    bucket_by_id = {bucket.id: bucket for bucket in buckets}
    bucket_children = build_bucket_children_map(buckets)

    parent_map = {bucket.id: bucket.parent_id for bucket in buckets}

    def top_bucket_id(bucket_id: int) -> int:
        current = bucket_id
        while parent_map.get(current):
            current = parent_map[current]
        return current

    def path_to_root(bucket_id: int) -> list[int]:
        path = [bucket_id]
        current = bucket_id
        while parent_map.get(current):
            current = parent_map[current]
            path.append(current)
        return path

    selected_bucket = None
    if bucket_id is not None:
        selected_bucket = bucket_by_id.get(bucket_id)

    level_buckets = bucket_children.get(None, [])
    if selected_bucket is not None:
        level_buckets = bucket_children.get(selected_bucket.id, [])

    bucket_totals: dict[int | str, int] = defaultdict(int)
    unassigned_items: list[dict[str, object]] = []
    ignored_items: list[dict[str, object]] = []
    leaf_items: list[dict[str, object]] = []
    direct_items: list[dict[str, object]] = []

    for item_id, item in user_items.items():
        seconds = item_durations.get(item_id, 0)
        assignment = assignments.get(item_id)
        if assignment and assignment.is_ignored:
            ignored_items.append(
                {
                    "item": item,
                    "seconds": seconds,
                    "duration_display": format_seconds(seconds),
                }
            )
            continue

        if assignment and assignment.bucket_id:
            assigned_bucket_id = assignment.bucket_id
            if selected_bucket is None:
                bucket_totals[top_bucket_id(assigned_bucket_id)] += seconds
            else:
                path = path_to_root(assigned_bucket_id)
                if selected_bucket.id in path:
                    if level_buckets:
                        if assigned_bucket_id == selected_bucket.id:
                            direct_items.append(
                                {
                                    "item": item,
                                    "seconds": seconds,
                                    "duration_display": format_seconds(seconds),
                                }
                            )
                        else:
                            idx = path.index(selected_bucket.id)
                            if idx > 0:
                                child_id = path[idx - 1]
                                bucket_totals[child_id] += seconds
                    else:
                        leaf_items.append(
                            {
                                "item": item,
                                "seconds": seconds,
                                "duration_display": format_seconds(seconds),
                            }
                        )
            continue

        if selected_bucket is None and seconds > 0:
            unassigned_items.append(
                {
                    "item": item,
                    "seconds": seconds,
                    "duration_display": format_seconds(seconds),
                }
            )

    bucket_entries = []
    for bucket in level_buckets:
        bucket_entries.append(
            {
                "label": bucket.name,
                "seconds": bucket_totals.get(bucket.id, 0),
                "kind": "bucket",
                "bucket_id": bucket.id,
            }
        )
    bucket_entries = sorted(bucket_entries, key=lambda x: x["seconds"], reverse=True)

    item_entries = []
    if selected_bucket is None:
        for row in unassigned_items:
            item_entries.append(
                {
                    "label": row["item"].display_title,
                    "seconds": row["seconds"],
                    "kind": "item",
                    "item_id": row["item"].id,
                }
            )
        item_entries = sorted(item_entries, key=lambda x: x["seconds"], reverse=True)
    elif selected_bucket is not None and not level_buckets:
        for row in leaf_items:
            item_entries.append(
                {
                    "label": row["item"].display_title,
                    "seconds": row["seconds"],
                    "kind": "item",
                    "item_id": row["item"].id,
                }
            )
        item_entries = sorted(item_entries, key=lambda x: x["seconds"], reverse=True)
    elif selected_bucket is not None and level_buckets:
        for row in direct_items:
            item_entries.append(
                {
                    "label": row["item"].display_title,
                    "seconds": row["seconds"],
                    "kind": "item",
                    "item_id": row["item"].id,
                }
            )
        item_entries = sorted(item_entries, key=lambda x: x["seconds"], reverse=True)

    selected = bucket_entries[:top_n]
    remaining_slots = max(0, top_n - len(selected))
    selected_items = item_entries[:remaining_slots]

    overflow_seconds = sum(x["seconds"] for x in bucket_entries[top_n:])
    overflow_seconds += sum(x["seconds"] for x in item_entries[remaining_slots:])

    entries = selected + selected_items
    if overflow_seconds > 0:
        entries.append(
            {
                "label": "Others",
                "seconds": overflow_seconds,
                "kind": "overflow",
            }
        )

    max_seconds = max((entry["seconds"] for entry in entries), default=0)
    for entry in entries:
        if max_seconds > 0:
            entry["percent"] = round(entry["seconds"] / max_seconds * 100, 2)
        else:
            entry["percent"] = 0
        entry["duration_display"] = format_seconds(entry["seconds"])

    ignored_items = sorted(ignored_items, key=lambda x: x["seconds"], reverse=True)
    unassigned_items = sorted(unassigned_items, key=lambda x: x["seconds"], reverse=True)

    return {
        "entries": entries,
        "total_seconds": sum(item_durations.values()),
        "total_display": format_seconds(sum(item_durations.values())),
        "unassigned_items": unassigned_items,
        "ignored_items": ignored_items,
        "selected_bucket": selected_bucket,
    }


def build_bucket_option_list(
    buckets: list[TimeBucket],
    *,
    exclude_ids: set[int] | None = None,
) -> list[dict[str, object]]:
    bucket_children = build_bucket_children_map(buckets)
    options: list[dict[str, object]] = []
    exclude_ids = exclude_ids or set()

    def walk(parent_id: int | None, depth: int):
        for bucket in bucket_children.get(parent_id, []):
            if bucket.id in exclude_ids:
                continue
            prefix = "--" * depth
            label = f"{prefix} {bucket.name}".strip()
            options.append({"id": bucket.id, "label": label})
            walk(bucket.id, depth + 1)

    walk(None, 0)
    return options
