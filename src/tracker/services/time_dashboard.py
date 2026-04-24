from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import NotRequired, TypedDict

from django.db.models import Sum

from ..models import (
    TimeBucket,
    TimeBucketAssignment,
    TimeLayout,
    UserItem,
    UserItemHistory,
)


class BucketItem(TypedDict):
    item_id: int
    title: str
    seconds: int
    duration_display: str
    percent: float
    item_share_percent: int


class BucketNode(TypedDict):
    id: int
    name: str
    depth: int
    indent_px: int
    seconds: int
    duration_display: str
    items: list[BucketItem]
    children: list[BucketNode]
    is_expanded: bool
    entries: list[BucketEntry]
    percent: float
    bucket_share_percent: int


class BucketEntry(TypedDict):
    kind: str
    seconds: int
    name: str
    node: NotRequired[BucketNode]
    nodes: NotRequired[list[BucketNode]]
    item: NotRequired[BucketItem]


class ContextItem(TypedDict):
    item: UserItem
    seconds: int
    duration_display: str


def _bucket_id(bucket: TimeBucket) -> int | None:
    value = getattr(bucket, "id", None)
    return value if isinstance(value, int) else None


def _bucket_parent_id(bucket: TimeBucket) -> int | None:
    value = getattr(bucket, "parent_id", None)
    return value if isinstance(value, int) else None


def _assignment_bucket_id(assignment: TimeBucketAssignment) -> int | None:
    value = getattr(assignment, "bucket_id", None)
    return value if isinstance(value, int) else None


def _assignment_user_item_id(assignment: TimeBucketAssignment) -> int:
    value = getattr(assignment, "user_item_id", None)
    if isinstance(value, int):
        return value
    raise ValueError("TimeBucketAssignment.user_item_id is not an int")


def _item_id(item: UserItem) -> int:
    value = getattr(item, "id", None)
    if isinstance(value, int):
        return value
    raise ValueError("UserItem.id is not an int")


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
    parent_map: dict[int, int | None] = {}
    for bucket in buckets:
        bucket_id = _bucket_id(bucket)
        if bucket_id is None:
            continue
        parent_map[bucket_id] = _bucket_parent_id(bucket)
    paths: dict[int, list[int]] = {}

    def path_for(bucket_id: int) -> list[int]:
        if bucket_id in paths:
            return paths[bucket_id]
        path = [bucket_id]
        current = bucket_id
        while parent_map.get(current) is not None:
            parent = parent_map[current]
            if parent is None:
                break
            path.append(parent)
            current = parent
        paths[bucket_id] = path
        return path

    for bucket in buckets:
        bucket_id = _bucket_id(bucket)
        if bucket_id is not None:
            path_for(bucket_id)

    return paths


def build_bucket_children_map(
    buckets: list[TimeBucket],
) -> dict[int | None, list[TimeBucket]]:
    bucket_children: dict[int | None, list[TimeBucket]] = defaultdict(list)
    for bucket in buckets:
        bucket_children[_bucket_parent_id(bucket)].append(bucket)
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
            child_id = _bucket_id(child)
            if child_id is None:
                continue
            child_ids.add(child_id)
            child_ids.update(collect(child_id))
        descendants[bucket_id] = child_ids
        return child_ids

    for bucket in buckets:
        bucket_id = _bucket_id(bucket)
        if bucket_id is None:
            continue
        collect(bucket_id)

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
    sort_dir: str = "desc",
) -> dict[str, object]:
    bucket_by_id: dict[int, TimeBucket] = {}
    for bucket in buckets:
        current_bucket_id = _bucket_id(bucket)
        if current_bucket_id is not None:
            bucket_by_id[current_bucket_id] = bucket
    bucket_children = build_bucket_children_map(buckets)

    parent_map: dict[int, int | None] = {}
    for bucket in buckets:
        current_bucket_id = _bucket_id(bucket)
        if current_bucket_id is not None:
            parent_map[current_bucket_id] = _bucket_parent_id(bucket)

    def path_to_root(bucket_id: int) -> list[int]:
        path = [bucket_id]
        current = bucket_id
        while True:
            parent = parent_map.get(current)
            if parent is None:
                break
            path.append(parent)
            current = parent
        return path

    selected_bucket = None
    if bucket_id is not None:
        selected_bucket = bucket_by_id.get(bucket_id)

    default_expand_depth = max(1, expand_depth)

    allowed_bucket_ids: set[int] = set()
    for bucket in buckets:
        current_bucket_id = _bucket_id(bucket)
        if current_bucket_id is not None:
            allowed_bucket_ids.add(current_bucket_id)
    if selected_bucket is not None:
        selected_bucket_id = _bucket_id(selected_bucket)
        if selected_bucket_id is None:
            selected_bucket = None
        else:
            descendants = build_bucket_descendants(buckets)
            allowed_bucket_ids = {selected_bucket_id} | descendants.get(
                selected_bucket_id, set()
            )

    bucket_seconds: dict[int, int] = defaultdict(int)
    bucket_items: dict[int, list[BucketItem]] = defaultdict(list)
    unassigned_items: list[ContextItem] = []
    ignored_items: list[ContextItem] = []

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

        if assignment:
            assigned_bucket_id = _assignment_bucket_id(assignment)
        else:
            assigned_bucket_id = None
        if assigned_bucket_id is not None:
            if assigned_bucket_id not in allowed_bucket_ids:
                continue
            if include_zero_time or seconds > 0:
                bucket_items[assigned_bucket_id].append(
                    {
                        "item_id": _item_id(item),
                        "title": item.display_title,
                        "seconds": seconds,
                        "duration_display": format_seconds(seconds),
                        "percent": 0.0,
                        "item_share_percent": 0,
                    }
                )
            if seconds > 0:
                path = path_to_root(assigned_bucket_id)
                if selected_bucket is not None:
                    selected_bucket_id = _bucket_id(selected_bucket)
                    if selected_bucket_id is None or selected_bucket_id not in path:
                        continue
                    path = path[: path.index(selected_bucket_id) + 1]
                for path_bucket_id in path:
                    if path_bucket_id in allowed_bucket_ids:
                        bucket_seconds[path_bucket_id] += seconds
            continue

        if selected_bucket is None and seconds > 0:
            unassigned_items.append(
                {
                    "item": item,
                    "seconds": seconds,
                    "duration_display": format_seconds(seconds),
                }
            )

    def bucket_sort_key(node: BucketNode) -> tuple[int, str]:
        seconds = node["seconds"]
        name = node["name"].lower()
        if sort_dir == "asc":
            return (seconds, name)
        return (-seconds, name)

    def item_sort_key(item: BucketItem) -> tuple[int, str]:
        seconds = item["seconds"]
        name = item["title"].lower()
        if sort_dir == "asc":
            return (seconds, name)
        return (-seconds, name)

    def entry_sort_key(entry: BucketEntry) -> tuple[int, str]:
        seconds = entry["seconds"]
        name = entry["name"].lower()
        if sort_dir == "asc":
            return (seconds, name)
        return (-seconds, name)

    def build_node(bucket: TimeBucket, depth: int) -> BucketNode | None:
        bucket_id = _bucket_id(bucket)
        if bucket_id is None or bucket_id not in allowed_bucket_ids:
            return None
        child_nodes: list[BucketNode] = []
        for child in bucket_children.get(bucket_id, []):
            child_result = build_node(child, depth + 1)
            if child_result is not None:
                child_nodes.append(child_result)
        items = bucket_items.get(bucket_id, [])
        items = sorted(items, key=item_sort_key)
        seconds = bucket_seconds.get(bucket_id, 0)
        bucket_node: BucketNode = {
            "id": bucket_id,
            "name": bucket.name,
            "depth": depth,
            "indent_px": depth * 16,
            "seconds": seconds,
            "duration_display": format_seconds(seconds),
            "items": items,
            "children": child_nodes,
            "is_expanded": depth < default_expand_depth,
            "entries": [],
            "percent": 0.0,
            "bucket_share_percent": 0,
        }
        entries: list[BucketEntry] = []
        for child_node in child_nodes:
            entries.append(
                {
                    "kind": "bucket",
                    "node": child_node,
                    "nodes": [child_node],
                    "seconds": child_node["seconds"],
                    "name": child_node["name"],
                }
            )
        for item in items:
            entries.append(
                {
                    "kind": "item",
                    "item": item,
                    "seconds": item["seconds"],
                    "name": item["title"],
                }
            )
        bucket_node["entries"] = sorted(entries, key=entry_sort_key)
        if include_zero_time or seconds > 0 or items or child_nodes:
            return bucket_node
        return None

    root_buckets = bucket_children.get(None, [])
    if selected_bucket is not None:
        root_buckets = [selected_bucket]

    bucket_tree = [
        node for bucket in root_buckets if (node := build_node(bucket, 0)) is not None
    ]
    bucket_tree = sorted(bucket_tree, key=bucket_sort_key)

    def collect_max(nodes: list[BucketNode]) -> int:
        max_value = 0
        for node in nodes:
            max_value = max(max_value, node["seconds"])
            for item in node["items"]:
                max_value = max(max_value, item["seconds"])
            max_value = max(max_value, collect_max(node["children"]))
        return max_value

    def apply_percent(nodes: list[BucketNode], max_value: int) -> None:
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

    def apply_share_percent(nodes: list[BucketNode], parent_seconds: int) -> None:
        for node in nodes:
            if parent_seconds > 0:
                node["bucket_share_percent"] = int(
                    node["seconds"] / parent_seconds * 100
                )
            else:
                node["bucket_share_percent"] = 0
            bucket_seconds = node["seconds"]
            for item in node["items"]:
                if bucket_seconds > 0:
                    item["item_share_percent"] = int(
                        item["seconds"] / bucket_seconds * 100
                    )
                else:
                    item["item_share_percent"] = 0
            apply_share_percent(node["children"], bucket_seconds)

    max_seconds = collect_max(bucket_tree)
    apply_percent(bucket_tree, max_seconds)
    root_seconds = sum(node["seconds"] for node in bucket_tree)
    apply_share_percent(bucket_tree, root_seconds)

    ignored_items = sorted(ignored_items, key=lambda x: x["seconds"], reverse=True)
    unassigned_items = sorted(
        unassigned_items, key=lambda x: x["seconds"], reverse=True
    )

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
            bucket_id = _bucket_id(bucket)
            if bucket_id is None:
                continue
            if bucket_id in exclude_ids:
                continue
            prefix = "--" * depth
            label = f"{prefix} {bucket.name}".strip()
            options.append({"id": bucket_id, "label": label})
            walk(bucket_id, depth + 1)

    walk(None, 0)
    return options
