from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Value
from django.db.models.functions import Coalesce
from django.urls import reverse

from .models import Profile, UserItem


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
            "pinned_more_count": 0,
            "current_item": None,
        }

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
    pinned = list(pinned_qs[:10])
    pinned_more_count = max(0, pinned_qs.count() - len(pinned))

    pinned_items = [
        {
            "id": item.pk,
            "title": item.display_title,
            "detail_url": reverse("useritem_detail", args=[item.pk]),
            "start_url": reverse("useritem_timer_start", args=[item.pk]),
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
            }

    return {
        "active_timers": active,
        "active_timer_current_id": current_id,
        "pinned_items": pinned_items,
        "pinned_more_count": pinned_more_count,
        "current_item": current_item,
    }
