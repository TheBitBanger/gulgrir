from typing import cast

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Value
from django.db.models.functions import Coalesce
from django.urls import reverse

from .models import FocusSprint, Profile, UserItem
from .services.focus_sprint import (
    build_ghost_suggestion,
    build_open_sprint_snapshots,
    format_minutes_short,
)
from .services.time_layouts import (
    build_assignment_labels_for_items,
    resolve_default_layout,
)


def _django_fmt(strftime_fmt: str) -> str:
    """Convert a limited subset of strftime tokens to Django date-filter
    codes."""
    return strftime_fmt.replace("%d", "d").replace("%m", "m").replace("%Y", "Y")


def date_format(request):
    if request.user.is_authenticated and hasattr(request.user, "profile"):
        p = request.user.profile

        return {
            "date_fmt": p.date_format,
            "fp_fmt": p.flatpickr_format(),
            "tpl_fmt": _django_fmt(p.date_format),
        }

    # fallback ISO
    return {
        "date_fmt": "%Y-%m-%d",
        "fp_fmt": "Y-m-d",
        "tpl_fmt": "Y-m-d",
    }


def theme_preference(request):
    if request.user.is_authenticated:
        try:
            preference = request.user.profile.theme
        except ObjectDoesNotExist:
            preference = Profile.Theme.SYSTEM

        return {"theme_preference": preference}

    return {"theme_preference": ""}


def active_timers(request):
    env_value = getattr(settings, "GULGRIR_ENV", "dev")
    env_map = {
        "dev": ("DEV", "dev"),
        "staging": ("STAGING", "staging"),
        "production": ("PROD", "prod"),
    }
    env_name, env_tone = env_map.get(env_value, ("DEV", "dev"))

    if not request.user.is_authenticated:
        return {
            "active_timers": [],
            "active_timer_current_id": None,
            "pinned_items": [],
            "pinned_groups": [],
            "current_item": None,
            "current_default_layout_name": "n/a",
            "current_environment_name": env_name,
            "current_environment_tone": env_tone,
        }

    profile, _ = Profile.objects.get_or_create(user=request.user)
    _, default_layout = resolve_default_layout(
        user=request.user,
        profile=profile,
        persist_default=True,
    )

    current_id = None
    match = getattr(request, "resolver_match", None)
    if match and match.url_name == "useritem_detail" and match.kwargs.get("pk"):
        try:
            current_id = int(match.kwargs["pk"])
        except (TypeError, ValueError):
            current_id = None

    timers = (
        UserItem.objects.filter(user=request.user, timer_started_at__isnull=False)
        .select_related("item")
        .order_by("timer_started_at")
    )
    active = [
        {
            "id": timer.pk,
            "title": timer.display_title,
            "started_at": timer.timer_started_at,
        }
        for timer in timers
    ]
    active_ids = {timer.pk for timer in timers}

    pinned_qs = (
        UserItem.objects.filter(
            user=request.user,
            is_pinned=True,
            timer_started_at__isnull=True,
        )
        .exclude(pk__in=active_ids)
        .exclude(pk=current_id or 0)
        .select_related("item")
        .annotate(sort_title=Coalesce("title_override", "item__title", Value("")))
        .order_by("sort_title", "pk")
    )
    pinned = list(pinned_qs)

    pinned_items = [
        {
            "id": item.pk,
            "title": item.display_title,
            "detail_url": reverse("useritem_detail", args=[item.pk]),
            "start_url": reverse("useritem_timer_start", args=[item.pk]),
            "bucket_label": "Unassigned",
        }
        for item in pinned
    ]

    current_item = None
    if current_id:
        current = (
            UserItem.objects.filter(user=request.user, pk=current_id)
            .select_related("item")
            .first()
        )
        if current:
            current_item = {
                "id": current.pk,
                "title": current.display_title,
                "detail_url": reverse("useritem_detail", args=[current.pk]),
                "is_pinned": current.is_pinned,
                "timer_started_at": current.timer_started_at,
                "start_url": reverse("useritem_timer_start", args=[current.pk]),
                "pin_url": reverse("useritem_pin", args=[current.pk]),
                "unpin_url": reverse("useritem_unpin", args=[current.pk]),
                "bucket_label": "Unassigned",
            }

    item_ids: set[int] = {cast(int, timer["id"]) for timer in active}
    item_ids.update(cast(int, item["id"]) for item in pinned_items)
    if current_item:
        item_ids.add(cast(int, current_item["id"]))

    bucket_labels_by_item = build_assignment_labels_for_items(
        layout=default_layout,
        item_ids=item_ids,
    )

    for timer in active:
        timer_id = cast(int, timer["id"])
        timer["bucket_label"] = bucket_labels_by_item.get(timer_id, "Unassigned")
    for pinned_item in pinned_items:
        pinned_id = cast(int, pinned_item["id"])
        pinned_item["bucket_label"] = bucket_labels_by_item.get(
            pinned_id,
            "Unassigned",
        )
    if current_item is not None:
        current_id = cast(int, current_item["id"])
        current_item["bucket_label"] = bucket_labels_by_item.get(
            current_id,
            "Unassigned",
        )

    grouped: dict[str, list[dict[str, object]]] = {}
    for pinned_item in pinned_items:
        label = cast(str, pinned_item["bucket_label"])
        if label not in grouped:
            grouped[label] = []
        grouped[label].append(pinned_item)

    pinned_groups = []
    ordered_labels = sorted(
        (label for label in grouped if label != "Unassigned"),
        key=str.lower,
    )
    if "Unassigned" in grouped:
        ordered_labels.append("Unassigned")

    for label in ordered_labels:
        items = grouped[label]
        pinned_groups.append(
            {
                "label": label,
                "items": items,
                "count": len(items),
            }
        )

    return {
        "active_timers": active,
        "active_timer_current_id": current_id,
        "pinned_items": pinned_items,
        "pinned_groups": pinned_groups,
        "current_item": current_item,
        "current_default_layout_name": default_layout.name if default_layout else "n/a",
        "current_environment_name": env_name,
        "current_environment_tone": env_tone,
    }


def saved_filters_sidebar(request):
    if not request.user.is_authenticated:
        return {
            "global_saved_filters": [],
            "global_active_filter_id": None,
            "focus_open_sprints": [],
            "focus_ghost_suggestion": None,
        }

    active_filter_id = request.GET.get("sf")
    if active_filter_id is not None:
        try:
            active_filter_id = int(active_filter_id)
        except (TypeError, ValueError):
            active_filter_id = None

    open_sprints = build_open_sprint_snapshots(user=request.user)
    ghost = build_ghost_suggestion(user=request.user, sprints=open_sprints)
    profile, _ = Profile.objects.get_or_create(user=request.user)

    serialized_sprints = [
        {
            "id": sprint.sprint_id,
            "scope_type": sprint.scope_type,
            "scope_id": sprint.scope_id,
            "scope_label": sprint.scope_label,
            "target_minutes": sprint.target_minutes,
            "target_display": format_minutes_short(sprint.target_minutes),
            "cap_display": format_minutes_short(sprint.overflow_soft_cap_minutes),
            "tracked_display": format_minutes_short(sprint.tracked_minutes),
            "target_logged_display": format_minutes_short(
                min(sprint.tracked_minutes, sprint.target_minutes)
            ),
            "overflow_logged_display": format_minutes_short(
                max(0, sprint.tracked_minutes - sprint.target_minutes)
            ),
            "stage": sprint.stage,
            "progress_percent": sprint.progress_percent,
            "completion_percent": sprint.completion_percent,
            "overflow_percent": sprint.overflow_percent,
            "target_share_percent": sprint.target_share_percent,
            "overflow_used_total_percent": sprint.overflow_used_total_percent,
            "scope_url": sprint.scope_url,
            "close_url": sprint.close_url,
        }
        for sprint in open_sprints
    ]

    return {
        "global_saved_filters": list(
            request.user.saved_filters.all().only("id", "name", "definition")
        ),
        "global_active_filter_id": active_filter_id,
        "focus_open_sprints": serialized_sprints,
        "focus_ghost_suggestion": ghost,
        "focus_scope_type_choices": FocusSprint.ScopeType,
    }
