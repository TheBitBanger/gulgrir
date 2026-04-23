import re
from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from tracker.actions import registry as action_registry

from ..forms import UserItemFilterForm, UserItemForm
from ..models import SavedFilter, Tag, TimeBucket, TimeLayout, UserItem, UserItemHistory
from ..services import build_useritem_queryset
from ..services.time_dashboard import build_bucket_option_list
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

    try:
        parsed = datetime.strptime(raw, "%H:%M").time()
    except ValueError:
        return time(0, 0), "Enter a valid time (HH:MM)"

    return parsed, None


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

    return ctx


class UserItemCreate(LoginRequiredMixin, CreateView):
    form_class = UserItemForm
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

        ctx["enable_tag_picker"] = True
        ctx["all_tags"] = list(
            Tag.objects.filter(user=self.request.user)
            .order_by("name")
            .values("id", "name")
        )

        form = ctx.get("form")
        if form is not None:
            raw = form["tags"].value() or []
            ctx["selected_tag_ids"] = [int(x) for x in raw]
        else:
            ctx["selected_tag_ids"] = []

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

        ctx["enable_tag_picker"] = True
        ctx["all_tags"] = list(
            Tag.objects.filter(user=self.request.user)
            .order_by("name")
            .values("id", "name")
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

        ctx["enable_tag_picker"] = True
        ctx["all_tags"] = list(
            Tag.objects.filter(user=self.request.user)
            .order_by("name")
            .values("id", "name")
        )

        form = ctx.get("form")
        if form is not None:
            raw = form["tags"].value() or []
            ctx["selected_tag_ids"] = [int(x) for x in raw]
        else:
            ctx["selected_tag_ids"] = []

        layouts = list(
            TimeLayout.objects.filter(user=self.request.user).order_by("order", "name")
        )
        if not layouts:
            layouts = list(
                TimeLayout.objects.filter(
                    user=self.request.user,
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

        ctx["item"] = user_item.item
        history_entries = []
        for entry in user_item.history.order_by("-happened_at"):
            duration = entry.duration
            if duration is None and entry.started_at and entry.ended_at:
                duration = entry.ended_at - entry.started_at
            history_entries.append(
                {
                    "entry": entry,
                    "duration_display": format_duration(duration),
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

        ctx["retro_values"] = {
            "date": timezone.localdate().isoformat(),
            "start_time": "",
            "duration": "",
        }
        ctx["retro_errors"] = {}
        ctx["can_restart_item"] = can_restart(user_item)

        return ctx

    def get_success_url(self):
        return reverse("useritem_detail", kwargs={"pk": self.object.pk})


class UserItemDelete(OwnObjectsMixin, DeleteView):
    model = UserItem
    success_url = reverse_lazy("useritem_dashboard")
    template_name = "tracker/confirm_delete.html"


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
        retro_values = {
            "date": date_raw or timezone.localdate().isoformat(),
            "start_time": time_raw,
            "duration": duration_raw,
        }
        form = UserItemForm(instance=user_item, user=request.user)
        ctx = build_useritem_detail_context(
            request=request,
            user_item=user_item,
            form=form,
            retro_values=retro_values,
            retro_errors=retro_errors,
        )
        return render(request, "tracker/useritem_detail.html", ctx, status=400)

    assert parsed_date is not None
    assert parsed_duration is not None

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

    return redirect("useritem_detail", pk=user_item.pk)
