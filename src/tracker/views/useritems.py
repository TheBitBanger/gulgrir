import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any, cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from tracker.actions import registry as action_registry

from ..forms import UserItemCreateForm, UserItemFilterForm, UserItemForm
from ..models import (
    Item,
    Profile,
    SavedFilter,
    Tag,
    TimeBucket,
    TimeLayout,
    UserItem,
    UserItemHistory,
)
from ..services import build_useritem_queryset
from ..services.time_dashboard import build_bucket_option_list
from ..services.time_layouts import (
    build_assignment_labels_for_items,
    resolve_default_layout,
)
from ..services.useritem_lifecycle import can_restart, mark_completed, restart_item
from .mixins import OwnObjectsMixin


def format_duration(duration) -> str:
    if duration is None:
        return "00:00:00"
    total_seconds = int(duration.total_seconds())
    if total_seconds < 0:
        total_seconds = 0
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_duration_input(duration: timedelta | None) -> str:
    if duration is None:
        return ""
    total_seconds = int(duration.total_seconds())
    if total_seconds <= 0:
        return ""
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def parse_retro_duration(raw: str) -> tuple[timedelta | None, str | None]:
    if not raw:
        return None, "Duration required"

    pattern = re.compile(r"(\d+)\s*([hms])", re.IGNORECASE)
    matches = list(pattern.finditer(raw))
    if not matches:
        return None, "Use h/m/s (e.g. 1h 20m 10s)"

    remainder = pattern.sub("", raw).strip()
    if remainder:
        return None, "Use h/m/s (e.g. 1h 20m 10s)"

    total_seconds = 0
    for match in matches:
        value = int(match.group(1))
        unit = match.group(2).lower()
        if unit == "h":
            total_seconds += value * 3600
        elif unit == "m":
            total_seconds += value * 60
        elif unit == "s":
            total_seconds += value

    if total_seconds <= 0 or total_seconds > 86400:
        if total_seconds <= 0:
            return None, "Duration required"
        return None, "Duration must be 24h or less"

    return timedelta(seconds=total_seconds), None


def parse_retro_date(raw: str, request) -> tuple[date | None, str | None]:
    if not raw:
        return None, "Enter a valid date"

    fmt = "%Y-%m-%d"
    if request.user.is_authenticated:
        profile = getattr(request.user, "profile", None)
        if profile and profile.date_format:
            fmt = profile.date_format

    try:
        return datetime.strptime(raw, fmt).date(), None
    except ValueError:
        pass

    try:
        return datetime.strptime(raw, "%Y-%m-%d").date(), None
    except ValueError:
        return None, "Enter a valid date"


def parse_retro_time(raw: str) -> tuple[time, str | None]:
    if not raw:
        return time(0, 0), None

    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", raw)
    if match is None:
        return time(0, 0), "Enter a valid time (HH:MM)"

    hour = int(match.group(1))
    minute = int(match.group(2))
    return time(hour, minute), None


def parse_local_datetime(raw: str) -> tuple[datetime | None, str | None]:
    if not raw:
        return None, "Enter a valid date and time"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None, "Enter a valid date and time"

    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    else:
        parsed = parsed.astimezone(timezone.get_current_timezone())

    return parsed, None


def parse_iso_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def resolve_entry_duration(entry: UserItemHistory) -> timedelta | None:
    duration = entry.duration
    if duration is None and entry.started_at and entry.ended_at:
        duration = entry.ended_at - entry.started_at
    return duration


def entry_reference_datetime(entry: UserItemHistory) -> datetime:
    if entry.ended_at:
        return entry.ended_at
    if entry.happened_at:
        return entry.happened_at
    if entry.started_at:
        return entry.started_at
    return timezone.now()


def build_grouped_history_entries(
    user_item: UserItem,
    *,
    day_limit: int,
    before_day: date | None,
) -> dict[str, object]:
    groups: list[dict[str, object]] = []
    has_more = False
    today = timezone.localdate()

    queryset = user_item.history.order_by("-happened_at", "-pk")
    for entry in queryset.iterator(chunk_size=200):
        reference_dt = timezone.localtime(entry_reference_datetime(entry))
        local_day = reference_dt.date()
        if before_day is not None and local_day >= before_day:
            continue

        duration = resolve_entry_duration(entry)
        row = {
            "entry": entry,
            "duration_display": format_duration(duration),
            "duration_input": format_duration_input(duration),
            "has_timing": bool(entry.started_at and entry.ended_at),
        }

        if not groups or groups[-1]["day"] != local_day:
            if len(groups) >= day_limit:
                has_more = True
                break
            groups.append(
                {
                    "day": local_day,
                    "entries": [],
                    "day_total_seconds": 0,
                    "session_count": 0,
                    "is_collapsed": local_day < (today - timedelta(days=6)),
                }
            )

        current_group = groups[-1]
        current_group_entries = cast(list[dict[str, object]], current_group["entries"])
        current_group_entries.append(row)
        if duration:
            current_group["day_total_seconds"] = int(
                cast(int, current_group["day_total_seconds"])
                + int(duration.total_seconds())
            )
            current_group["session_count"] = int(
                cast(int, current_group["session_count"]) + 1
            )

    for group in groups:
        group["day_total_display"] = format_duration(
            timedelta(seconds=int(cast(int, group["day_total_seconds"])))
        )
        entries = cast(list[dict[str, object]], group["entries"])
        group["preview_entries"] = entries[:3]
        group["hidden_entries"] = entries[3:]
        group["hidden_count"] = max(0, len(entries) - 3)

    next_before = None
    if has_more and groups:
        next_before = cast(date, groups[-1]["day"]).isoformat()

    return {
        "groups": groups,
        "has_more": has_more,
        "next_before": next_before,
    }


def build_time_tracking_summary(user_item: UserItem) -> dict[str, object]:
    timed_qs = user_item.history.filter(
        event_type=UserItemHistory.Event.REVISITED,
        duration__isnull=False,
        ended_at__isnull=False,
    )

    tz = timezone.get_current_timezone()
    local_today = timezone.localdate()
    last_7_start = timezone.make_aware(
        datetime.combine(local_today - timedelta(days=6), time.min),
        tz,
    )
    last_30_start = timezone.make_aware(
        datetime.combine(local_today - timedelta(days=29), time.min),
        tz,
    )

    totals = timed_qs.aggregate(
        total=Sum("duration"),
        sessions=Count("id"),
        last_tracked=Max("ended_at"),
        last_7=Sum("duration", filter=Q(ended_at__gte=last_7_start)),
        last_30=Sum("duration", filter=Q(ended_at__gte=last_30_start)),
    )

    total = cast(timedelta | None, totals["total"]) or timedelta()
    sessions = int(cast(int | None, totals["sessions"]) or 0)
    active_days: set[date] = set()
    for entry in timed_qs.only("ended_at").iterator(chunk_size=200):
        if entry.ended_at is None:
            continue
        active_days.add(timezone.localtime(entry.ended_at).date())
    active_day_count = len(active_days)
    average_per_day = (total / active_day_count) if active_day_count > 0 else None

    return {
        "total_display": format_duration(total),
        "last_7_display": format_duration(
            cast(timedelta | None, totals["last_7"]) or timedelta()
        ),
        "last_30_display": format_duration(
            cast(timedelta | None, totals["last_30"]) or timedelta()
        ),
        "avg_per_day_display": format_duration(average_per_day),
        "active_day_count": active_day_count,
        "session_count": sessions,
        "last_tracked": totals["last_tracked"],
    }


def day_month_format(date_format: str | None) -> str:
    fmt = (date_format or "").strip() or "%d/%m/%Y"
    reduced = fmt.replace("%Y", "").replace("%y", "")

    while "//" in reduced:
        reduced = reduced.replace("//", "/")
    while "--" in reduced:
        reduced = reduced.replace("--", "-")
    while ".." in reduced:
        reduced = reduced.replace("..", ".")

    reduced = reduced.strip("/-. ")
    if not reduced:
        return "%d/%m"
    return reduced


def build_time_tracking_trend(
    user_item: UserItem,
    *,
    day_count: int = 30,
    before_day: date | None = None,
    date_format: str | None = None,
) -> list[dict[str, object]]:
    if day_count < 1:
        return []

    end_day = before_day - timedelta(days=1) if before_day else timezone.localdate()
    start_day = end_day - timedelta(days=day_count - 1)

    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(start_day, time.min), tz)
    end_dt = timezone.make_aware(
        datetime.combine(end_day + timedelta(days=1), time.min),
        tz,
    )

    totals_by_day: dict[date, int] = defaultdict(int)
    entries = user_item.history.filter(
        event_type=UserItemHistory.Event.REVISITED,
        duration__isnull=False,
        ended_at__gte=start_dt,
        ended_at__lt=end_dt,
    ).only("ended_at", "duration")
    for entry in entries:
        if entry.ended_at is None or entry.duration is None:
            continue
        local_day = timezone.localtime(entry.ended_at).date()
        totals_by_day[local_day] += int(entry.duration.total_seconds())

    max_seconds = max(totals_by_day.values(), default=0)
    tick_format = day_month_format(date_format)
    trend: list[dict[str, object]] = []
    for offset in range(day_count):
        day = start_day + timedelta(days=offset)
        seconds = totals_by_day.get(day, 0)
        height_percent = 0
        if max_seconds > 0 and seconds > 0:
            height_percent = max(10, int((seconds / max_seconds) * 100))
        if max_seconds > 0 and seconds > 0:
            bar_opacity = 0.2 + (seconds / max_seconds) * 0.8
        else:
            bar_opacity = 0.12
        trend.append(
            {
                "day": day,
                "seconds": seconds,
                "duration_display": format_duration(timedelta(seconds=seconds)),
                "height_percent": height_percent,
                "bar_opacity": f"{bar_opacity:.2f}",
                "is_tick": offset % 7 == 0,
                "tick_label": day.strftime(tick_format),
                "anchor_id": f"history-day-{day.isoformat()}",
            }
        )

    return trend


def build_useritem_detail_context(
    request,
    user_item: UserItem,
    form,
    retro_values: dict[str, str],
    retro_errors: dict[str, str],
):
    ctx: dict[str, object] = {}
    ctx["form"] = form
    ctx["object"] = user_item
    ctx["item"] = user_item.item
    ctx["enable_tag_picker"] = True
    ctx["all_tags"] = list(
        Tag.objects.filter(user=request.user).order_by("name").values("id", "name")
    )

    raw = form["tags"].value() or []
    ctx["selected_tag_ids"] = [int(x) for x in raw]

    history_entries = []
    for entry in user_item.history.order_by("-happened_at"):
        duration = entry.duration
        if duration is None and entry.started_at and entry.ended_at:
            duration = entry.ended_at - entry.started_at
        history_entries.append(
            {
                "entry": entry,
                "duration_display": format_duration(duration),
                "duration_input": format_duration_input(duration),
            }
        )
    ctx["history_entries"] = history_entries
    ctx["last_completed_at"] = (
        user_item.history.filter(event_type=UserItemHistory.Event.COMPLETED)
        .order_by("-happened_at")
        .values_list("happened_at", flat=True)
        .first()
    )
    ctx["last_revisited_at"] = (
        user_item.history.filter(event_type=UserItemHistory.Event.REVISITED)
        .order_by("-happened_at")
        .values_list("happened_at", flat=True)
        .first()
    )
    ctx["timer_started_at"] = user_item.timer_started_at
    ctx["timer_is_running"] = user_item.timer_started_at is not None
    if user_item.timer_started_at:
        ctx["timer_duration_display"] = format_duration(
            timezone.now() - user_item.timer_started_at
        )
    else:
        ctx["timer_duration_display"] = format_duration(None)

    ctx["retro_values"] = retro_values
    ctx["retro_errors"] = retro_errors

    profile, _ = Profile.objects.get_or_create(user=request.user)
    _, default_layout = resolve_default_layout(
        user=request.user,
        profile=profile,
        persist_default=True,
    )
    assignment_labels = build_assignment_labels_for_items(
        layout=default_layout,
        item_ids={user_item.id},
    )
    ctx["assignment_indicator"] = {
        "layout_name": default_layout.name if default_layout else "n/a",
        "bucket_label": assignment_labels.get(user_item.id, "Unassigned"),
    }

    return ctx


class UserItemCreate(LoginRequiredMixin, CreateView):
    form_class = UserItemCreateForm
    model = UserItem
    template_name = "tracker/form.html"
    success_url = reverse_lazy("useritem_dashboard")
    extra_context = {"model_verbose": UserItem._meta.verbose_name}

    def form_valid(self, form):
        form.instance.user = self.request.user
        if form.instance.created_by_id is None:
            form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user

        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = cast(Any, self.request.user)

        ctx["enable_tag_picker"] = True
        ctx["all_tags"] = list(
            Tag.objects.filter(user=user).order_by("name").values("id", "name")
        )

        form = ctx.get("form")
        if form is not None:
            raw = form["tags"].value() or []
            ctx["selected_tag_ids"] = [int(x) for x in raw]
        else:
            ctx["selected_tag_ids"] = []

        ctx["enable_item_suggestions"] = True
        ctx["item_suggestions_url"] = reverse("useritem_item_suggestions")

        return ctx


class UserItemUpdate(OwnObjectsMixin, UpdateView):
    form_class = UserItemForm
    model = UserItem
    template_name = "tracker/form.html"
    success_url = reverse_lazy("useritem_dashboard")
    extra_context = {"model_verbose": UserItem._meta.verbose_name}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user

        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = cast(Any, self.request.user)

        ctx["enable_tag_picker"] = True
        ctx["all_tags"] = list(
            Tag.objects.filter(user=user).order_by("name").values("id", "name")
        )

        form = ctx["form"]
        raw = form["tags"].value() or []
        ctx["selected_tag_ids"] = [int(x) for x in raw]

        return ctx


class UserItemDetail(OwnObjectsMixin, UpdateView):
    form_class = UserItemForm
    model = UserItem
    template_name = "tracker/useritem_detail.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user

        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user_item = self.object
        user = cast(Any, self.request.user)

        ctx["enable_tag_picker"] = True
        ctx["all_tags"] = list(
            Tag.objects.filter(user=user).order_by("name").values("id", "name")
        )

        form = ctx.get("form")
        if form is not None:
            raw = form["tags"].value() or []
            ctx["selected_tag_ids"] = [int(x) for x in raw]
        else:
            ctx["selected_tag_ids"] = []

        layouts = list(TimeLayout.objects.filter(user=user).order_by("order", "name"))
        if not layouts:
            layouts = list(
                TimeLayout.objects.filter(
                    user=user,
                    assignments__user_item=user_item,
                )
                .distinct()
                .order_by("order", "name")
            )
        bucket_options_by_layout: dict[str, list[dict[str, object]]] = {}
        for layout in layouts:
            buckets = list(
                TimeBucket.objects.filter(layout=layout).select_related("parent")
            )
            bucket_options_by_layout[str(layout.id)] = build_bucket_option_list(buckets)
        ctx["assignment_layouts"] = layouts
        ctx["bucket_options_by_layout"] = bucket_options_by_layout

        profile, _ = Profile.objects.get_or_create(user=user)
        _, default_layout = resolve_default_layout(
            user=user,
            profile=profile,
            persist_default=True,
        )
        assignment_labels = build_assignment_labels_for_items(
            layout=default_layout,
            item_ids={user_item.id},
        )
        ctx["assignment_indicator"] = {
            "layout_name": default_layout.name if default_layout else "n/a",
            "bucket_label": assignment_labels.get(user_item.id, "Unassigned"),
        }

        ctx["item"] = user_item.item
        before_day = parse_iso_date(self.request.GET.get("history_before"))
        grouped_history = build_grouped_history_entries(
            user_item,
            day_limit=30,
            before_day=before_day,
        )
        next_before = cast(str | None, grouped_history["next_before"])
        history_load_older_url = None
        if next_before:
            history_load_older_url = (
                f"{reverse('useritem_detail', kwargs={'pk': user_item.pk})}"
                f"?history_before={next_before}"
            )
        ctx["time_summary"] = build_time_tracking_summary(user_item)
        ctx["history_trend"] = build_time_tracking_trend(
            user_item,
            day_count=30,
            before_day=before_day,
            date_format=profile.date_format,
        )
        ctx["history_day_groups"] = grouped_history["groups"]
        ctx["history_has_more"] = grouped_history["has_more"]
        ctx["history_load_older_url"] = history_load_older_url
        ctx["history_window_days"] = 30
        ctx["history_full_page_url"] = reverse(
            "useritem_time_history", kwargs={"pk": user_item.pk}
        )
        ctx["last_completed_at"] = (
            user_item.history.filter(event_type=UserItemHistory.Event.COMPLETED)
            .order_by("-happened_at")
            .values_list("happened_at", flat=True)
            .first()
        )
        ctx["last_revisited_at"] = (
            user_item.history.filter(event_type=UserItemHistory.Event.REVISITED)
            .order_by("-happened_at")
            .values_list("happened_at", flat=True)
            .first()
        )
        ctx["timer_started_at"] = user_item.timer_started_at
        ctx["timer_is_running"] = user_item.timer_started_at is not None
        if user_item.timer_started_at:
            ctx["timer_duration_display"] = format_duration(
                timezone.now() - user_item.timer_started_at
            )
        else:
            ctx["timer_duration_display"] = format_duration(None)

        ctx["retro_values"] = {
            "date": timezone.localdate().isoformat(),
            "start_time": "",
            "duration": "",
        }
        ctx["retro_errors"] = {}
        ctx["can_restart_item"] = can_restart(user_item)
        user_items_for_reassign = list(
            UserItem.objects.filter(user=user).select_related("item")
        )
        user_items_for_reassign.sort(key=lambda row: row.display_title.lower())
        ctx["history_reassign_options"] = user_items_for_reassign

        return ctx

    def get_success_url(self):
        return reverse("useritem_detail", kwargs={"pk": self.object.pk})


class UserItemDelete(OwnObjectsMixin, DeleteView):
    model = UserItem
    success_url = reverse_lazy("useritem_dashboard")
    template_name = "tracker/confirm_delete.html"


@login_required
def useritem_time_history(request, pk: int):
    user_item = get_object_or_404(
        UserItem.objects.select_related("item"),
        pk=pk,
        user=request.user,
    )
    before_day = parse_iso_date(request.GET.get("history_before"))
    grouped_history = build_grouped_history_entries(
        user_item,
        day_limit=30,
        before_day=before_day,
    )

    user_items_for_reassign = list(
        UserItem.objects.filter(user=request.user).select_related("item")
    )
    user_items_for_reassign.sort(key=lambda row: row.display_title.lower())
    profile, _ = Profile.objects.get_or_create(user=request.user)

    history_load_older_url = None
    next_before = cast(str | None, grouped_history["next_before"])
    if next_before:
        history_load_older_url = (
            f"{reverse('useritem_time_history', kwargs={'pk': user_item.pk})}"
            f"?history_before={next_before}"
        )

    return render(
        request,
        "tracker/useritem_time_history.html",
        {
            "object": user_item,
            "item": user_item.item,
            "time_summary": build_time_tracking_summary(user_item),
            "history_trend": build_time_tracking_trend(
                user_item,
                day_count=30,
                before_day=before_day,
                date_format=profile.date_format,
            ),
            "history_day_groups": grouped_history["groups"],
            "history_has_more": grouped_history["has_more"],
            "history_load_older_url": history_load_older_url,
            "history_window_days": 30,
            "history_full_page_url": reverse(
                "useritem_time_history", kwargs={"pk": user_item.pk}
            ),
            "history_reassign_options": user_items_for_reassign,
        },
    )


@require_POST
@login_required
def useritem_complete(request, pk: int):
    user_item = get_object_or_404(UserItem, pk=pk, user=request.user)
    mark_completed(user_item)
    messages.success(request, "Item marked as completed.")
    return redirect("useritem_detail", pk=user_item.pk)


@require_POST
@login_required
def useritem_restart(request, pk: int):
    user_item = get_object_or_404(UserItem, pk=pk, user=request.user)
    try:
        restart_item(user_item)
    except ValueError:
        messages.error(request, "Item cannot be restarted yet.")
    else:
        messages.success(request, "Item marked as redoing.")

    return redirect("useritem_detail", pk=user_item.pk)


@login_required
def useritem_dashboard(request):
    default_group = "selector"
    actions_default = [a for a in action_registry.values() if a.group == default_group]

    saved_filters = request.user.saved_filters.all()
    active_filter = None
    if sf_id := request.GET.get("sf"):
        active_filter = (
            SavedFilter.objects.filter(pk=sf_id, user=request.user)
            .only("id", "name", "definition", "user")
            .first()
        )

    data = request.GET.copy()
    data.pop("sf", None)
    form = UserItemFilterForm(data, user=request.user)

    items = build_useritem_queryset(request)

    if request.headers.get("HX-Request"):
        ctx = {
            "form": UserItemFilterForm(request.GET or None, user=request.user),
            "items": items,
            "saved_filters": saved_filters,
            "active_filter": active_filter,
        }

        return render(request, "tracker/partials/useritem_filter.html", ctx)

    return render(
        request,
        "tracker/useritem_dashboard.html",
        {
            "form": form,
            "saved_filters": saved_filters,
            "items": items,
            "actions": action_registry.values(),
            "actions_default": actions_default,
            "active_filter": active_filter,
        },
    )


@require_POST
@login_required
def useritem_timer_start(request, pk: int):
    with transaction.atomic():
        user_item = get_object_or_404(
            UserItem.objects.select_for_update(), pk=pk, user=request.user
        )
        if user_item.timer_started_at:
            return JsonResponse({"error": "Timer already running"}, status=409)
        user_item.timer_started_at = timezone.now()
        user_item.save(update_fields=["timer_started_at"])

    return JsonResponse({"started_at": user_item.timer_started_at.isoformat()})


@require_POST
@login_required
def useritem_pin(request, pk: int):
    user_item = get_object_or_404(UserItem, pk=pk, user=request.user)
    if not user_item.is_pinned:
        user_item.is_pinned = True
        user_item.save(update_fields=["is_pinned"])
    return JsonResponse({"ok": True})


@require_POST
@login_required
def useritem_unpin(request, pk: int):
    user_item = get_object_or_404(UserItem, pk=pk, user=request.user)
    if user_item.is_pinned:
        user_item.is_pinned = False
        user_item.save(update_fields=["is_pinned"])
    return JsonResponse({"ok": True})


@require_POST
@login_required
def useritem_timer_stop(request, pk: int):
    with transaction.atomic():
        user_item = get_object_or_404(
            UserItem.objects.select_for_update(), pk=pk, user=request.user
        )
        if not user_item.timer_started_at:
            return JsonResponse({"error": "Timer is not running"}, status=409)

        started_at = user_item.timer_started_at
        ended_at = timezone.now()
        history = UserItemHistory(
            user_item=user_item,
            event_type=UserItemHistory.Event.REVISITED,
            happened_at=ended_at,
            started_at=started_at,
            ended_at=ended_at,
        )
        history.save()

        user_item.timer_started_at = None
        user_item.save(update_fields=["timer_started_at"])

    return JsonResponse(
        {
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "duration": history.duration.total_seconds() if history.duration else 0,
        }
    )


@require_POST
@login_required
def useritem_timer_add_retro(request, pk: int):
    user_item = get_object_or_404(UserItem, pk=pk, user=request.user)
    date_raw = (request.POST.get("retro_date") or "").strip()
    time_raw = (request.POST.get("retro_start_time") or "").strip()
    duration_raw = (request.POST.get("retro_duration") or "").strip()

    retro_errors: dict[str, str] = {}

    parsed_date, date_error = parse_retro_date(date_raw, request)
    if date_error:
        retro_errors["Date"] = date_error

    parsed_time, time_error = parse_retro_time(time_raw)
    if time_error:
        retro_errors["Start time"] = time_error

    parsed_duration, duration_error = parse_retro_duration(duration_raw)
    if duration_error:
        retro_errors["Duration"] = duration_error

    if retro_errors:
        for field, message in retro_errors.items():
            messages.error(request, f"{field}: {message}")
        return redirect("useritem_detail", pk=user_item.pk)

    if parsed_date is None or parsed_duration is None:
        if parsed_date is None:
            messages.error(request, "Date: Enter a valid date")
        if parsed_duration is None:
            messages.error(request, "Duration: Duration required")
        return redirect("useritem_detail", pk=user_item.pk)

    tz = timezone.get_current_timezone()
    started_at = timezone.make_aware(datetime.combine(parsed_date, parsed_time), tz)
    ended_at = started_at + parsed_duration
    history = UserItemHistory(
        user_item=user_item,
        event_type=UserItemHistory.Event.REVISITED,
        happened_at=ended_at,
        started_at=started_at,
        ended_at=ended_at,
    )
    history.save()

    messages.success(request, "Retro time entry added.")

    return redirect("useritem_detail", pk=user_item.pk)


@require_POST
@login_required
def useritem_history_update(request, pk: int, history_pk: int):
    user_item = get_object_or_404(UserItem, pk=pk, user=request.user)
    with transaction.atomic():
        history_entry = get_object_or_404(
            UserItemHistory.objects.select_for_update(),
            pk=history_pk,
            user_item=user_item,
            event_type=UserItemHistory.Event.REVISITED,
        )

        started_raw = (request.POST.get("started_at") or "").strip()
        mode = (request.POST.get("edit_mode") or "end").strip().lower()
        ended_raw = (request.POST.get("ended_at") or "").strip()
        duration_raw = (request.POST.get("duration") or "").strip()
        target_raw = (request.POST.get("target_user_item") or "").strip()

        started_at, started_error = parse_local_datetime(started_raw)
        if started_error:
            messages.error(request, f"Start: {started_error}")
            return redirect("useritem_detail", pk=user_item.pk)
        if started_at is None:
            messages.error(request, "Start: Enter a valid date and time")
            return redirect("useritem_detail", pk=user_item.pk)

        ended_at: datetime
        if mode == "duration":
            parsed_duration, duration_error = parse_retro_duration(duration_raw)
            if duration_error:
                messages.error(request, f"Duration: {duration_error}")
                return redirect("useritem_detail", pk=user_item.pk)
            if parsed_duration is None:
                messages.error(request, "Duration: Duration required")
                return redirect("useritem_detail", pk=user_item.pk)
            ended_at = started_at + parsed_duration
        else:
            parsed_ended_at, ended_error = parse_local_datetime(ended_raw)
            if ended_error:
                messages.error(request, f"End: {ended_error}")
                return redirect("useritem_detail", pk=user_item.pk)
            if parsed_ended_at is None:
                messages.error(request, "End: Enter a valid date and time")
                return redirect("useritem_detail", pk=user_item.pk)
            ended_at = parsed_ended_at
            if ended_at <= started_at:
                messages.error(request, "End: Must be after start")
                return redirect("useritem_detail", pk=user_item.pk)

        target_user_item = user_item
        if target_raw:
            target_user_item = get_object_or_404(
                UserItem,
                pk=target_raw,
                user=request.user,
            )

        history_entry.user_item = target_user_item
        history_entry.started_at = started_at
        history_entry.ended_at = ended_at
        history_entry.happened_at = ended_at
        history_entry.save(
            update_fields=[
                "user_item",
                "started_at",
                "ended_at",
                "happened_at",
                "duration",
            ]
        )

    messages.success(request, "Time entry updated.")
    next_url = (request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("useritem_detail", pk=target_user_item.pk)


@login_required
def useritem_item_suggestions(request):
    query = (request.GET.get("q") or "").strip()
    media_type = (request.GET.get("media_type") or "").strip()
    if not query or media_type not in Item.MediaType.values:
        return JsonResponse({"results": []})

    queryset = Item.objects.filter(
        title__icontains=query,
        media_type=media_type,
    )

    results = list(
        queryset.order_by("title", "id").values("id", "title", "media_type")[:10]
    )

    return JsonResponse({"results": results})
