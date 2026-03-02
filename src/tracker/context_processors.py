from django.core.exceptions import ObjectDoesNotExist

from .models import Profile


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
