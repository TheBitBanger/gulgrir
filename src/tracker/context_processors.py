from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Value
from django.db.models.functions import Coalesce
from django.urls import reverse

from .models import Profile, UserItem
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
    if not request.user.is_authenticated:
        return {
            "active_timers": [],
            "active_timer_current_id": None,
            "pinned_items": [],
            "current_item": None,
            "current_default_layout_name": "n/a",
            "current_environment_name": "n/a",
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

    item_ids = {timer["id"] for timer in active}
    item_ids.update(item["id"] for item in pinned_items)
    if current_item:
        item_ids.add(current_item["id"])

    bucket_labels_by_item = build_assignment_labels_for_items(
        layout=default_layout,
        item_ids=item_ids,
    )

    for timer in active:
        timer["bucket_label"] = bucket_labels_by_item.get(timer["id"], "Unassigned")
    for pinned_item in pinned_items:
        pinned_item["bucket_label"] = bucket_labels_by_item.get(
            pinned_item["id"],
            "Unassigned",
        )
    if current_item is not None:
        current_item["bucket_label"] = bucket_labels_by_item.get(
            current_item["id"],
            "Unassigned",
        )

    return {
        "active_timers": active,
        "active_timer_current_id": current_id,
        "pinned_items": pinned_items,
        "current_item": current_item,
        "current_default_layout_name": default_layout.name if default_layout else "n/a",
        "current_environment_name": "n/a",
    }


def saved_filters_sidebar(request):
    if not request.user.is_authenticated:
        return {
            "global_saved_filters": [],
            "global_active_filter_id": None,
        }

    active_filter_id = request.GET.get("sf")
    if active_filter_id is not None:
        try:
            active_filter_id = int(active_filter_id)
        except (TypeError, ValueError):
            active_filter_id = None

    return {
        "global_saved_filters": list(
            request.user.saved_filters.all().only("id", "name", "definition")
        ),
        "global_active_filter_id": active_filter_id,
    }
