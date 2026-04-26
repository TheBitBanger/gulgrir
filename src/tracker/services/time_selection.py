from __future__ import annotations

import random
from datetime import date, datetime, time
from typing import TypedDict

from django.urls import reverse

from ..models import TimeBucket, TimeBucketAssignment, TimeLayout, UserItem
from .selection import apply_selector_eligibility
from .time_dashboard import (
    build_bucket_children_map,
    build_bucket_paths,
    load_item_durations,
)
from .time_windows import day_range, find_time_window


class SelectionResult(TypedDict):
    id: int
    title: str
    kind: str
    url: str


class LevelEntry(TypedDict):
    kind: str
    id: int
    label: str
    seconds: int
    url: str


def select_from_level_for_user(
    *,
    user,
    layout_id: int,
    bucket_id: int | None,
    time_window_key: str | None,
    range_start: date | None = None,
    range_end: date | None = None,
    day_cutoff: time | None = None,
) -> SelectionResult | None:
    layout = TimeLayout.objects.filter(user=user, id=layout_id).first()
    if layout is None:
        raise ValueError("Layout not found.")

    if bucket_id is not None:
        bucket_exists = TimeBucket.objects.filter(id=bucket_id, layout=layout).exists()
        if not bucket_exists:
            raise ValueError("Bucket not found.")

    buckets = list(TimeBucket.objects.filter(layout=layout).select_related("parent"))
    bucket_children = build_bucket_children_map(buckets)
    bucket_paths = build_bucket_paths(buckets)

    start: datetime | None
    end: datetime | None
    if range_start and range_end:
        start, _ = day_range(range_start, day_cutoff)
        _, end = day_range(range_end, day_cutoff)
    else:
        window = find_time_window(time_window_key, day_cutoff) or find_time_window(
            "all_time", day_cutoff
        )
        start = window.start if window else None
        end = window.end if window else None
    durations = load_item_durations(user, start, end)

    assignments = list(
        TimeBucketAssignment.objects.filter(
            layout=layout,
        ).select_related("bucket", "user_item", "user_item__item")
    )

    bucket_totals: dict[int, int] = {}
    for assignment in assignments:
        if assignment.assignment_mode != TimeBucketAssignment.Mode.BUCKET:
            continue
        if assignment.bucket_id is None:
            continue
        duration = durations.get(assignment.user_item_id, 0)
        for bucket_id_in_path in bucket_paths.get(assignment.bucket_id, []):
            bucket_totals[bucket_id_in_path] = (
                bucket_totals.get(bucket_id_in_path, 0) + duration
            )

    candidate_buckets = bucket_children.get(bucket_id, [])
    if bucket_id is None:
        candidate_assignments = [
            assignment
            for assignment in assignments
            if assignment.assignment_mode == TimeBucketAssignment.Mode.TOP_LEVEL
        ]
    else:
        candidate_assignments = [
            assignment
            for assignment in assignments
            if assignment.assignment_mode == TimeBucketAssignment.Mode.BUCKET
            and assignment.bucket_id == bucket_id
        ]
    candidate_item_ids = {a.user_item_id for a in candidate_assignments}
    eligible_items = {
        item.id: item
        for item in apply_selector_eligibility(
            UserItem.objects.filter(user=user, id__in=candidate_item_ids)
        ).select_related("item")
    }

    entries: list[LevelEntry] = []
    for bucket in candidate_buckets:
        seconds = bucket_totals.get(bucket.id, 0)
        dashboard_url = (
            f"{reverse('time_dashboard')}?layout={layout.id}&bucket={bucket.id}"
        )
        entries.append(
            {
                "kind": "bucket",
                "id": bucket.id,
                "label": bucket.name,
                "seconds": seconds,
                "url": dashboard_url,
            }
        )

    for assignment in candidate_assignments:
        item = eligible_items.get(assignment.user_item_id)
        if not item:
            continue
        seconds = durations.get(item.id, 0)
        entries.append(
            {
                "kind": "item",
                "id": item.id,
                "label": item.display_title,
                "seconds": seconds,
                "url": reverse("useritem_detail", kwargs={"pk": item.id}),
            }
        )

    if not entries:
        return None

    weights = [1.0 / (entry["seconds"] + 1) for entry in entries]
    # Feature-level weighted selection; cryptographic randomness is not required.
    chosen = random.choices(entries, weights=weights, k=1)[0]  # nosec B311
    return {
        "id": int(chosen["id"]),
        "title": str(chosen["label"]),
        "kind": str(chosen["kind"]),
        "url": str(chosen["url"]),
    }
