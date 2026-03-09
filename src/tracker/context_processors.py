from django.core.exceptions import ObjectDoesNotExist

from .models import Profile, UserItem


def _django_fmt(strftime_fmt: str) -> str:
    """Convert a limited subset of strftime tokens to Django date-filter
        codes."""
    return (
        strftime_fmt
        .replace("%d", "d")
        .replace("%m", "m")
        .replace("%Y", "Y")
    )


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
        return {"active_timers": [], "active_timer_current_id": None}

    current_id = None
    match = getattr(request, "resolver_match", None)
    if match and match.kwargs.get("pk"):
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

    return {"active_timers": active, "active_timer_current_id": current_id}
