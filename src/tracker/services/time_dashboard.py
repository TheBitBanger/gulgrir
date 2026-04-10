from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from django.db.models import Sum
from django.utils import timezone

from ..models import TimeBucket, TimeBucketAssignment, TimeLayout, UserItem, UserItemHistory
from .time_windows import day_range


def format_seconds(total_seconds: int) -> str:
    if total_seconds <= 0:
        return "00:00:00"
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


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
    include_zero_time: bool = False,
    expand_depth: int = 3,
) -> dict[str, object]:
    bucket_by_id = {bucket.id: bucket for bucket in buckets}
    bucket_children = build_bucket_children_map(buckets)

    parent_map = {bucket.id: bucket.parent_id for bucket in buckets}

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

    default_expand_depth = max(1, expand_depth)

    allowed_bucket_ids: set[int] = {
        bucket.id for bucket in buckets if bucket.id is not None
    }
    if selected_bucket is not None:
        descendants = build_bucket_descendants(buckets)
        allowed_bucket_ids = {selected_bucket.id} | descendants.get(
            selected_bucket.id, set()
        )

    bucket_seconds: dict[int, int] = defaultdict(int)
    bucket_items: dict[int, list[dict[str, object]]] = defaultdict(list)
    unassigned_items: list[dict[str, object]] = []
    ignored_items: list[dict[str, object]] = []

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
            if assigned_bucket_id not in allowed_bucket_ids:
                continue
            if include_zero_time or seconds > 0:
                bucket_items[assigned_bucket_id].append(
                    {
                        "item_id": item.id,
                        "title": item.display_title,
                        "seconds": seconds,
                        "duration_display": format_seconds(seconds),
                    }
                )
            if seconds > 0:
                path = path_to_root(assigned_bucket_id)
                if selected_bucket is not None:
                    if selected_bucket.id not in path:
                        continue
                    path = path[: path.index(selected_bucket.id) + 1]
                for bucket_id in path:
                    if bucket_id in allowed_bucket_ids:
                        bucket_seconds[bucket_id] += seconds
            continue

        if selected_bucket is None and seconds > 0:
            unassigned_items.append(
                {
                    "item": item,
                    "seconds": seconds,
                    "duration_display": format_seconds(seconds),
                }
            )

    def build_node(bucket: TimeBucket, depth: int) -> dict[str, object] | None:
        if bucket.id is None or bucket.id not in allowed_bucket_ids:
            return None
        child_nodes: list[dict[str, object]] = []
        for child in bucket_children.get(bucket.id, []):
            node = build_node(child, depth + 1)
            if node is not None:
                child_nodes.append(node)
        items = bucket_items.get(bucket.id, [])
        items = sorted(items, key=lambda x: x["seconds"], reverse=True)
        seconds = bucket_seconds.get(bucket.id, 0)
        node = {
            "id": bucket.id,
            "name": bucket.name,
            "depth": depth,
            "indent_px": depth * 16,
            "seconds": seconds,
            "duration_display": format_seconds(seconds),
            "items": items,
            "children": child_nodes,
            "is_expanded": depth < default_expand_depth,
        }
        if include_zero_time or seconds > 0 or items or child_nodes:
            return node
        return None

    root_buckets = bucket_children.get(None, [])
    if selected_bucket is not None:
        root_buckets = [selected_bucket]

    bucket_tree = [
        node
        for bucket in root_buckets
        if (node := build_node(bucket, 0)) is not None
    ]

    def collect_max(nodes: list[dict[str, object]]) -> int:
        max_value = 0
        for node in nodes:
            max_value = max(max_value, int(node["seconds"]))
            for item in node["items"]:
                max_value = max(max_value, int(item["seconds"]))
            max_value = max(max_value, collect_max(node["children"]))
        return max_value

    def apply_percent(nodes: list[dict[str, object]], max_value: int) -> None:
        for node in nodes:
            if max_value > 0:
                node["percent"] = round(node["seconds"] / max_value * 100, 2)
            else:
                node["percent"] = 0
            for item in node["items"]:
                if max_value > 0:
                    item["percent"] = round(item["seconds"] / max_value * 100, 2)
                else:
                    item["percent"] = 0
            apply_percent(node["children"], max_value)

    max_seconds = collect_max(bucket_tree)
    apply_percent(bucket_tree, max_seconds)

    ignored_items = sorted(ignored_items, key=lambda x: x["seconds"], reverse=True)
    unassigned_items = sorted(unassigned_items, key=lambda x: x["seconds"], reverse=True)

    return {
        "bucket_tree": bucket_tree,
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
