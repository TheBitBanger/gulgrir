from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from ..models import (
    FocusSprint,
    Profile,
    TimeBucket,
    TimeBucketAssignment,
    TimeLayout,
    UserItemHistory,
)
from .time_dashboard import build_bucket_descendants
from .time_layouts import resolve_default_layout
from .time_selection import select_from_level_for_user
from .time_windows import day_range


@dataclass
class SprintSnapshot:
    sprint_id: int
    scope_type: str
    scope_id: int
    scope_label: str
    target_minutes: int
    overflow_soft_cap_minutes: int
    tracked_minutes: int
    threshold_minutes: int
    stage: str
    progress_percent: int
    completion_percent: int
    overflow_percent: int
    scope_url: str
    close_url: str


def _duration_minutes(duration: timedelta | None) -> int:
    if duration is None:
        return 0
    seconds = int(duration.total_seconds())
    if seconds <= 0:
        return 0
    return seconds // 60


def format_minutes_short(minutes: int) -> str:
    if minutes <= 0:
        return "0m"
    hours = minutes // 60
    rem = minutes % 60
    if hours and rem:
        return f"{hours}h {rem}m"
    if hours:
        return f"{hours}h"
    return f"{rem}m"


def parse_goal_input_minutes(raw: str) -> int | None:
    value = (raw or "").strip().lower()
    if not value:
        return None
    if value.isdigit():
        return int(value) * 60

    total = 0
    token = ""
    seen = False
    for ch in value:
        if ch.isdigit():
            token += ch
            continue
        if ch in {"h", "m"} and token:
            amount = int(token)
            total += amount * 60 if ch == "h" else amount
            token = ""
            seen = True
            continue
        if ch in {" ", "\t"}:
            continue
        return None

    if token:
        return None
    if not seen:
        return None
    return total


def profile_defaults(profile: Profile) -> dict[str, int]:
    return {
        "target_minutes": max(60, profile.focus_default_target_minutes),
        "overflow_soft_cap_minutes": max(
            0, profile.focus_default_overflow_soft_cap_minutes
        ),
    }


def _scope_label(sprint: FocusSprint) -> str:
    if sprint.scope_type == sprint.ScopeType.ITEM and sprint.user_item is not None:
        return sprint.user_item.display_title
    if sprint.scope_type == sprint.ScopeType.BUCKET and sprint.time_bucket is not None:
        return sprint.time_bucket.name
    return "Unknown scope"


def _scope_url(sprint: FocusSprint) -> str:
    if sprint.scope_type == sprint.ScopeType.ITEM and sprint.user_item_id is not None:
        return reverse("useritem_detail", kwargs={"pk": sprint.user_item_id})
    if (
        sprint.scope_type == sprint.ScopeType.BUCKET
        and sprint.time_bucket_id is not None
    ):
        if sprint.time_bucket is not None:
            layout_id = sprint.time_bucket.layout_id
            return (
                reverse("time_dashboard")
                + f"?layout={layout_id}&bucket={sprint.time_bucket_id}"
            )
        return reverse("time_dashboard") + f"?bucket={sprint.time_bucket_id}"
    return reverse("useritem_dashboard")


def _scope_item_ids_for_bucket(*, sprint: FocusSprint, user: Any) -> set[int]:
    if sprint.time_bucket_id is None:
        return set()
    if sprint.time_bucket is None:
        return set()
    layout = TimeLayout.objects.filter(
        user=user,
        id=sprint.time_bucket.layout_id,
    ).first()
    if layout is None:
        return set()
    buckets = list(
        TimeBucket.objects.filter(layout=layout).only(
            "id", "parent_id", "name", "order"
        )
    )
    descendants = build_bucket_descendants(buckets)
    allowed_bucket_ids = {sprint.time_bucket_id} | descendants.get(
        sprint.time_bucket_id, set()
    )

    assignment_item_ids = set(
        TimeBucketAssignment.objects.filter(
            layout=layout,
            assignment_mode=TimeBucketAssignment.Mode.BUCKET,
            bucket_id__in=allowed_bucket_ids,
        ).values_list("user_item_id", flat=True)
    )
    return assignment_item_ids


def _tracked_minutes_for_sprint(*, sprint: FocusSprint, user: Any, cutoff_time) -> int:
    end = sprint.closed_at or timezone.now()
    started_local_day = timezone.localtime(sprint.started_at).date()
    start_floor, _ = day_range(started_local_day, cutoff_time)
    base_q = Q(
        event_type=UserItemHistory.Event.REVISITED,
        duration__isnull=False,
        started_at__isnull=False,
        ended_at__isnull=False,
        ended_at__gte=start_floor,
        started_at__lte=end,
        user_item__user=user,
    )

    if sprint.scope_type == sprint.ScopeType.ITEM and sprint.user_item_id is not None:
        q = base_q & Q(user_item_id=sprint.user_item_id)
    elif sprint.scope_type == sprint.ScopeType.BUCKET:
        item_ids = _scope_item_ids_for_bucket(sprint=sprint, user=user)
        if not item_ids:
            return 0
        q = base_q & Q(user_item_id__in=item_ids)
    else:
        return 0

    total_seconds = 0
    entries = UserItemHistory.objects.filter(q).only("started_at", "ended_at")
    for entry in entries:
        if entry.started_at is None or entry.ended_at is None:
            continue
        overlap_start = max(entry.started_at, start_floor)
        overlap_end = min(entry.ended_at, end)
        if overlap_end <= overlap_start:
            continue
        total_seconds += int((overlap_end - overlap_start).total_seconds())
    return _duration_minutes(timedelta(seconds=total_seconds))


def _stage_for(*, tracked: int, target: int, cap: int) -> tuple[str, int, int, int]:
    threshold = target + cap
    if target <= 0:
        target = 60
    ratio = tracked / target
    if ratio < 0.5:
        stage = "starved"
    elif ratio < 1.0:
        stage = "nourished"
    elif tracked < threshold:
        stage = "sated"
    else:
        stage = "gorged"

    progress_percent = min(100, int((tracked / target) * 100)) if target > 0 else 0
    completion_percent = int((tracked / target) * 100) if target > 0 else 0
    overflow_percent = 0
    if tracked > target and cap > 0:
        overflow_percent = min(100, int(((tracked - target) / cap) * 100))
    elif tracked >= threshold and cap == 0:
        overflow_percent = 100
    return stage, progress_percent, completion_percent, overflow_percent


def build_open_sprint_snapshots(*, user) -> list[SprintSnapshot]:
    profile, _ = Profile.objects.get_or_create(user=user)
    cutoff_time = profile.time_dashboard_day_cutoff
    open_sprints = list(
        user.focus_sprints.filter(closed_at__isnull=True)
        .select_related("user_item", "user_item__item", "time_bucket")
        .order_by("-started_at")
    )
    snapshots: list[SprintSnapshot] = []
    for sprint in open_sprints:
        tracked = _tracked_minutes_for_sprint(
            sprint=sprint,
            user=user,
            cutoff_time=cutoff_time,
        )
        stage, progress_percent, completion_percent, overflow_percent = _stage_for(
            tracked=tracked,
            target=sprint.target_minutes,
            cap=sprint.overflow_soft_cap_minutes,
        )
        snapshots.append(
            SprintSnapshot(
                sprint_id=sprint.id,
                scope_type=sprint.scope_type,
                scope_id=sprint.user_item_id
                if sprint.scope_type == sprint.ScopeType.ITEM
                else sprint.time_bucket_id or 0,
                scope_label=_scope_label(sprint),
                target_minutes=sprint.target_minutes,
                overflow_soft_cap_minutes=sprint.overflow_soft_cap_minutes,
                tracked_minutes=tracked,
                threshold_minutes=sprint.target_minutes
                + sprint.overflow_soft_cap_minutes,
                stage=stage,
                progress_percent=progress_percent,
                completion_percent=completion_percent,
                overflow_percent=overflow_percent,
                scope_url=_scope_url(sprint),
                close_url=reverse("focus_release", kwargs={"sprint_id": sprint.id}),
            )
        )
    return snapshots


def build_ghost_suggestion(
    *, user, sprints: list[SprintSnapshot]
) -> dict[str, Any] | None:
    profile, _ = Profile.objects.get_or_create(user=user)
    _, layout = resolve_default_layout(user=user, profile=profile, persist_default=True)
    if layout is None:
        return None
    open_item_ids = {
        snapshot.scope_id
        for snapshot in sprints
        if snapshot.scope_type == FocusSprint.ScopeType.ITEM
    }
    open_bucket_ids = {
        snapshot.scope_id
        for snapshot in sprints
        if snapshot.scope_type == FocusSprint.ScopeType.BUCKET
    }

    for _ in range(8):
        suggestion = select_from_level_for_user(
            user=user,
            layout_id=layout.id,
            bucket_id=None,
            time_window_key="all_time",
            day_cutoff=profile.time_dashboard_day_cutoff,
        )
        if suggestion is None:
            return None
        kind = str(suggestion["kind"])
        suggestion_id = int(suggestion["id"])
        if kind == "item" and suggestion_id in open_item_ids:
            continue
        if kind == "bucket" and suggestion_id in open_bucket_ids:
            continue
        return {
            "kind": kind,
            "id": suggestion_id,
            "title": suggestion["title"],
            "url": suggestion["url"],
        }
    return None
