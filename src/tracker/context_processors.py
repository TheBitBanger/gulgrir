from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Value
from django.db.models.functions import Coalesce
from django.urls import reverse

from .models import Profile, TimeBucket, TimeBucketAssignment, UserItem
from .services.time_layouts import resolve_default_layout


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
    pinned = list(pinned_qs[:10])
    pinned_more_count = max(0, pinned_qs.count() - len(pinned))

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

    bucket_labels_by_item: dict[int, str] = {}
    if default_layout and item_ids:
        assignments = list(
            TimeBucketAssignment.objects.filter(
                layout=default_layout,
                user_item_id__in=item_ids,
            ).select_related("bucket", "bucket__parent")
        )

        bucket_ids = {
            assignment.bucket_id
            for assignment in assignments
            if assignment.assignment_mode == TimeBucketAssignment.Mode.BUCKET
            and assignment.bucket_id is not None
        }
        bucket_by_id = {
            bucket.id: bucket
            for bucket in TimeBucket.objects.filter(
                layout=default_layout,
                id__in=bucket_ids,
            ).select_related("parent")
        }

        def bucket_path_label(bucket_id: int) -> str:
            names: list[str] = []
            current_bucket = bucket_by_id.get(bucket_id)
            seen: set[int] = set()
            while current_bucket is not None and current_bucket.id not in seen:
                seen.add(current_bucket.id)
                names.append(current_bucket.name)
                parent_id = current_bucket.parent_id
                current_bucket = (
                    bucket_by_id.get(parent_id) if parent_id is not None else None
                )
            if not names:
                return "Unassigned"
            return " / ".join(reversed(names))

        for assignment in assignments:
            if assignment.assignment_mode == TimeBucketAssignment.Mode.TOP_LEVEL:
                bucket_labels_by_item[assignment.user_item_id] = "Top level"
                continue
            if assignment.assignment_mode == TimeBucketAssignment.Mode.BUCKET:
                if assignment.bucket_id is not None:
                    bucket_labels_by_item[assignment.user_item_id] = bucket_path_label(
                        assignment.bucket_id
                    )
                else:
                    bucket_labels_by_item[assignment.user_item_id] = "Unassigned"
                continue
            bucket_labels_by_item[assignment.user_item_id] = "Ignored"

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
        "pinned_more_count": pinned_more_count,
        "current_item": current_item,
        "current_default_layout_name": default_layout.name if default_layout else "n/a",
        "current_environment_name": "n/a",
    }
