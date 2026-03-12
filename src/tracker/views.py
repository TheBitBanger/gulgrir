import json
import random
import re
import sys
from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django.views.generic.list import ListView

from tracker.actions import Action
from tracker.actions import registry as action_registry

from .forms import ProfileForm, TagForm, UserItemFilterForm, UserItemForm
from .models import (
    Item,
    Profile,
    SavedFilter,
    Tag,
    TimeBucket,
    TimeBucketAssignment,
    TimeLayout,
    UserItem,
    UserItemHistory,
)
from .services import build_useritem_queryset
from .services.selection import apply_selector_eligibility
from .services.time_dashboard import (
    build_bucket_children_map,
    build_bucket_descendants,
    build_bucket_option_list,
    build_bucket_paths,
    build_chart_entries,
    format_seconds,
    load_item_durations,
)
from .services.time_windows import build_time_windows, find_time_window


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
        Tag.objects.filter(user=request.user)
        .order_by("name")
        .values("id", "name")
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




@require_POST
@login_required
def bulk_history_action(request):
    """
    Re-usable endpoint that any list template can POST to with:
        action = 'completed' | 'revisited'
        selected_ids = repeated UserItem IDs (e.g. selected_ids=1&selected_ids=2)
    """
    action = request.POST.get("action")
    ids = request.POST.getlist("selected_ids")

    valid_actions = {
        "completed": UserItemHistory.Event.COMPLETED,
        "revisited": UserItemHistory.Event.REVISITED,
    }
    if action not in valid_actions or not ids:
        return redirect(request.META.get("HTTP_REFERER", "/"))

    queryset = UserItem.objects.filter(user=request.user, id__in=ids).select_related(
        "item"
    )

    # log history
    history_records = [
        UserItemHistory(user_item=ui, event_type=valid_actions[action])
        for ui in queryset
    ]
    UserItemHistory.objects.bulk_create(history_records)

    # also move shelf on 'completed'
    if action == "completed":
        queryset.update(shelf=UserItem.Shelf.DONE)

    return redirect(request.META.get("HTTP_REFERER", "/"))


class ItemCreate(LoginRequiredMixin, CreateView):
    model = Item
    fields = ["media_type", "title"]
    template_name = "tracker/form.html"
    success_url = reverse_lazy("item_list")
    extra_context = {"model_verbose": Item._meta.verbose_name}


class ItemList(LoginRequiredMixin, ListView):
    model = Item
    template_name = "tracker/item_list.html"
    paginate_by = 30


class OwnObjectsMixin(LoginRequiredMixin):
    """Mix-in that restricts queryset to the logged-in user."""

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)


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

    # Helper methods for tag pill selector
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

        # Prefer bound form values (POST with errors), otherwise empty list
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

    # Helper methods for tag pill selector
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
            bucket_options_by_layout[str(layout.id)] = build_bucket_option_list(
                buckets
            )
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
        ctx["can_restart_item"] = (
            ctx["last_completed_at"] is not None and not user_item.is_redoing
        )

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
    UserItemHistory.objects.create(
        user_item=user_item,
        event_type=UserItemHistory.Event.COMPLETED,
        happened_at=timezone.now(),
    )
    user_item.shelf = UserItem.Shelf.DONE
    user_item.is_redoing = False
    user_item.save(update_fields=["shelf", "is_redoing"])
    messages.success(request, "Item marked as completed.")
    return redirect("useritem_detail", pk=user_item.pk)


@require_POST
@login_required
def useritem_restart(request, pk: int):
    user_item = get_object_or_404(UserItem, pk=pk, user=request.user)
    has_completed = user_item.history.filter(
        event_type=UserItemHistory.Event.COMPLETED
    ).exists()
    if has_completed and not user_item.is_redoing:
        user_item.is_redoing = True
        user_item.shelf = UserItem.Shelf.IN_PROGRESS
        user_item.save(update_fields=["is_redoing", "shelf"])
        messages.success(request, "Item marked as redoing.")
    else:
        messages.error(request, "Item cannot be restarted yet.")

    return redirect("useritem_detail", pk=user_item.pk)


class TagCreate(LoginRequiredMixin, CreateView):
    model = Tag
    form_class = TagForm
    template_name = "tracker/form.html"
    success_url = reverse_lazy("tag_list")
    extra_context = {"model_verbose": Tag._meta.verbose_name}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user

        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class TagList(OwnObjectsMixin, ListView):
    model = Tag
    template_name = "tracker/tag_list.html"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(usage_count=Count("user_items"))
            .order_by("name")
        )


class TagUpdate(OwnObjectsMixin, UpdateView):
    model = Tag
    form_class = TagForm
    template_name = "tracker/form.html"
    success_url = reverse_lazy("tag_list")
    extra_context = {"model_verbose": Tag._meta.verbose_name}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user

        return kwargs


class TagDelete(OwnObjectsMixin, DeleteView):
    model = Tag
    template_name = "tracker/confirm_delete.html"
    success_url = reverse_lazy("tag_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["usage_count"] = self.object.user_items.count()

        return ctx


class SavedFilterList(OwnObjectsMixin, ListView):
    model = SavedFilter
    template_name = "tracker/saved_filter_list.html"


class SavedFilterUpdate(OwnObjectsMixin, UpdateView):
    model = SavedFilter
    fields = ["name"]
    template_name = "tracker/form.html"
    success_url = reverse_lazy("saved_filter_list")
    extra_context = {"model_verbose": SavedFilter._meta.verbose_name}


class SavedFilterDelete(OwnObjectsMixin, DeleteView):
    model = SavedFilter
    template_name = "tracker/confirm_delete.html"
    success_url = reverse_lazy("saved_filter_list")


@method_decorator(csrf_protect, name="dispatch")
class TagQuickCreate(LoginRequiredMixin, View):
    def post(self, request):
        # Accept JSON or form-encoded
        name = ""
        ctype = request.headers.get("Content-Type", "")
        try:
            if "application/json" in ctype:
                payload = json.loads(request.body.decode("utf-8") or "{}")
                name = (payload.get("name") or "").strip()
            else:
                name = (request.POST.get("name") or "").strip()
        except Exception:
            return JsonResponse({"error": "Invalid request"}, status=400)

        if not name:
            return JsonResponse({"error": "Tag name cannot be empty"}, status=400)
        if len(name) > 64:
            return JsonResponse({"error": "Tag name too long (max 64)"}, status=400)

        # Case-insensitive get-or-create
        existing = Tag.objects.filter(user=request.user, name__iexact=name).first()
        if existing:
            return JsonResponse({"id": existing.id, "name": existing.name})

        try:
            tag = Tag.objects.create(user=request.user, name=name)
            return JsonResponse({"id": tag.id, "name": tag.name})
        except IntegrityError:
            # In case of race/constraint collision
            existing = Tag.objects.filter(user=request.user, name__iexact=name).first()
            if existing:
                return JsonResponse({"id": existing.id, "name": existing.name})
            return JsonResponse({"error": "Could not create tag"}, status=400)


class PreferenceView(UpdateView):
    template_name = "tracker/preferences.html"
    model = Profile
    form_class = ProfileForm
    success_url = reverse_lazy("preferences")

    def get_object(self, queryset=None):
        # ensures profile exists even if for some reason it was not created
        profile, _ = Profile.objects.get_or_create(user=self.request.user)

        return profile


preference_view = login_required(PreferenceView.as_view())


@login_required
def useritem_dashboard(request):
    # default values for actions
    default_group = "selector"
    actions_default = [a for a in action_registry.values() if a.group == default_group]

    # pass saved filters for the sidebar
    saved_filters = request.user.saved_filters.all()
    active_filter = None
    if sf_id := request.GET.get("sf"):
        active_filter = (
            SavedFilter.objects.filter(pk=sf_id, user=request.user)
            .only("id", "name", "definition", "user")
            .first()
        )

    # pass the filter form status to all subsequent requests to restore state
    data = request.GET.copy()
    data.pop("sf", None)
    form = UserItemFilterForm(data, user=request.user)

    items = build_useritem_queryset(request)

    # htmx -------------------------------------------------------------------
    if request.headers.get("HX-Request"):
        target = request.headers.get("HX-Target", "")
        ctx = {
            "form": UserItemFilterForm(request.GET or None, user=request.user),
            "items": items,
            "saved_filters": saved_filters,
            "active_filter": active_filter,
        }

        return render(request, "tracker/partials/useritem_filter.html", ctx)
    # end htmx ---------------------------------------------------------------

    # full page render
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
def save_current_filter(request):
    form = UserItemFilterForm(request.POST, user=request.user)
    if not form.is_valid():
        return HttpResponseBadRequest("Invalid filter")

    # The filter name lives in a form field, so get it from POST
    name = (request.POST.get("filter_name") or "Unnamed").strip()
    definition = form.to_definition()
    active_filter_id = request.POST.get("active_filter_id")
    active_filter_name = request.POST.get("active_filter_name")

    if active_filter_id and active_filter_name and name == active_filter_name:
        sf = get_object_or_404(SavedFilter, pk=active_filter_id, user=request.user)
        sf.definition = definition
        sf.name = name
        sf.save()
    else:
        existing = SavedFilter.objects.filter(user=request.user, name=name).first()
        if existing:
            if request.POST.get("overwrite_existing") == "1":
                existing.definition = definition
                existing.save()
                sf = existing
            else:
                return HttpResponse(
                    "A saved filter with this name already exists. Update it instead?",
                    status=409,
                )
        else:
            sf = SavedFilter.objects.create(
                user=request.user,
                name=name,
                definition=definition,
            )

    url = f"{reverse('useritem_dashboard')}?{sf.query_params()}"
    resp = HttpResponse("")
    resp["HX-Redirect"] = url

    return resp


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
            "duration": history.duration.total_seconds()
            if history.duration
            else 0,
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
    started_at = timezone.make_aware(
        datetime.combine(parsed_date, parsed_time), tz
    )
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


@login_required
def time_dashboard(request):
    layouts = list(
        TimeLayout.objects.filter(user=request.user).order_by("order", "name")
    )
    layout = None
    if layouts:
        layout_id = request.GET.get("layout")
        if layout_id:
            layout = next((l for l in layouts if str(l.id) == layout_id), None)
        layout = layout or layouts[0]

    selected_bucket_id = request.GET.get("bucket")
    bucket_id = int(selected_bucket_id) if selected_bucket_id else None
    show_zero_time = request.GET.get("show_zero") == "1"

    buckets: list[TimeBucket] = []
    assignments: dict[int, TimeBucketAssignment] = {}
    user_items = {
        item.id: item
        for item in UserItem.objects.filter(user=request.user).select_related("item")
    }

    if layout:
        buckets = list(
            TimeBucket.objects.filter(layout=layout).select_related("parent")
        )
        assignments = {
            a.user_item_id: a
            for a in TimeBucketAssignment.objects.filter(layout=layout)
            .select_related("bucket")
        }

    daily_contexts: list[dict[str, object]] = []
    rolling_contexts: list[dict[str, object]] = []
    all_time_context: dict[str, object] = {"label": "All time", "entries": []}
    all_time_assignments = {
        "unassigned_items": [],
        "ignored_items": [],
        "selected_bucket": None,
    }
    selector_windows = []

    if layout:
        time_windows = build_time_windows()
        daily_windows = [w for w in time_windows if w.group == "daily"]
        rolling_windows = [w for w in time_windows if w.group == "rolling"]
        all_time_window = next(
            (w for w in time_windows if w.group == "all_time"), None
        )
        selector_windows = [
            {"key": w.key, "label": w.label} for w in time_windows
        ]

        def period_context(
            start: datetime | None,
            end: datetime | None,
            label: str,
            include_zero_time: bool,
        ):
            durations = load_item_durations(request.user, start, end)
            chart = build_chart_entries(
                layout=layout,
                buckets=buckets,
                assignments=assignments,
                item_durations=durations,
                user_items=user_items,
                bucket_id=bucket_id,
                top_n=None,
                include_zero_time=include_zero_time,
            )
            chart["label"] = label
            return chart

        for window in daily_windows:
            daily_contexts.append(
                period_context(
                    window.start,
                    window.end,
                    window.label,
                    include_zero_time=show_zero_time,
                )
            )

        for window in rolling_windows:
            include_zero_time = show_zero_time
            rolling_contexts.append(
                period_context(
                    window.start,
                    window.end,
                    window.label,
                    include_zero_time=include_zero_time,
                )
            )

        if all_time_window is not None:
            all_time_context = period_context(
                all_time_window.start,
                all_time_window.end,
                all_time_window.label,
                include_zero_time=show_zero_time,
            )
            all_time_durations = load_item_durations(
                request.user, all_time_window.start, all_time_window.end
            )
        else:
            all_time_durations = load_item_durations(request.user, None, None)

        all_time_assignments = build_chart_entries(
            layout=layout,
            buckets=buckets,
            assignments=assignments,
            item_durations=all_time_durations,
            user_items=user_items,
            bucket_id=None,
            top_n=None,
            include_zero_time=show_zero_time,
        )


    bucket_options = []
    if layout:
        bucket_options = build_bucket_option_list(buckets)

    bucket_by_id = {bucket.id: bucket for bucket in buckets}
    selected_bucket = bucket_by_id.get(bucket_id) if bucket_id else None
    breadcrumb_buckets: list[TimeBucket] = []
    if selected_bucket is not None:
        bucket_paths = build_bucket_paths(buckets)
        path_ids = list(reversed(bucket_paths.get(selected_bucket.id, [])))
        breadcrumb_buckets = [
            bucket_by_id[b_id] for b_id in path_ids if b_id in bucket_by_id
        ]

    return render(
        request,
        "tracker/time_dashboard.html",
        {
            "layouts": layouts,
            "layout": layout,
            "buckets": buckets,
            "bucket_options": bucket_options,
            "daily_contexts": daily_contexts,
            "rolling_contexts": rolling_contexts,
            "all_time_context": all_time_context,
            "unassigned_items": all_time_assignments["unassigned_items"],
            "ignored_items": all_time_assignments["ignored_items"],
            "selected_bucket": selected_bucket,
            "breadcrumb_buckets": breadcrumb_buckets,
            "selector_windows": selector_windows,
            "show_zero_time": show_zero_time,
        },
    )


@login_required
def time_settings(request):
    layouts = list(
        TimeLayout.objects.filter(user=request.user).order_by("order", "name")
    )
    layout = None
    if layouts:
        layout_id = request.GET.get("layout")
        if layout_id:
            layout = next((l for l in layouts if str(l.id) == layout_id), None)
        layout = layout or layouts[0]

    buckets: list[TimeBucket] = []
    if layout:
        buckets = list(
            TimeBucket.objects.filter(layout=layout).select_related("parent")
        )

    bucket_options = []
    bucket_management: list[dict[str, object]] = []
    assigned_items_by_bucket: dict[int, list[TimeBucketAssignment]] = {}
    if layout:
        bucket_options = build_bucket_option_list(buckets)
        bucket_children = build_bucket_children_map(buckets)
        bucket_descendants = build_bucket_descendants(buckets)
        assignments = list(
            TimeBucketAssignment.objects.filter(
                layout=layout,
                bucket__isnull=False,
                is_ignored=False,
            ).select_related("bucket", "user_item__item")
        )
        for assignment in assignments:
            if assignment.bucket_id is None:
                continue
            assigned_items_by_bucket.setdefault(assignment.bucket_id, []).append(
                assignment
            )
        for items in assigned_items_by_bucket.values():
            items.sort(key=lambda row: row.user_item.display_title.lower())

        def build_bucket_management(parent_id: int | None, depth: int) -> None:
            for bucket in bucket_children.get(parent_id, []):
                exclude_ids = {bucket.id} | bucket_descendants.get(bucket.id, set())
                bucket_management.append(
                    {
                        "bucket": bucket,
                        "depth": depth,
                        "has_children": bool(bucket_children.get(bucket.id)),
                        "items": assigned_items_by_bucket.get(bucket.id, []),
                        "parent_options": build_bucket_option_list(
                            buckets, exclude_ids=exclude_ids
                        ),
                    }
                )
                build_bucket_management(bucket.id, depth + 1)

        build_bucket_management(None, 0)

    return render(
        request,
        "tracker/time_settings.html",
        {
            "layouts": layouts,
            "layout": layout,
            "buckets": buckets,
            "bucket_options": bucket_options,
            "bucket_management": bucket_management,
        },
    )


@require_POST
@login_required
def time_level_select(request):
    layout_id = request.POST.get("layout_id")
    window_key = request.POST.get("time_window")
    bucket_id = request.POST.get("bucket_id")
    if not layout_id:
        return HttpResponseBadRequest("Missing layout")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    current_bucket_id = int(bucket_id) if bucket_id else None
    if current_bucket_id is not None:
        get_object_or_404(TimeBucket, id=current_bucket_id, layout=layout)

    buckets = list(TimeBucket.objects.filter(layout=layout).select_related("parent"))
    bucket_children = build_bucket_children_map(buckets)
    bucket_paths = build_bucket_paths(buckets)

    window = find_time_window(window_key) or find_time_window("all_time")
    start = window.start if window else None
    end = window.end if window else None
    durations = load_item_durations(request.user, start, end)

    assignments = list(
        TimeBucketAssignment.objects.filter(
            layout=layout,
            bucket__isnull=False,
            is_ignored=False,
        ).select_related("bucket", "user_item", "user_item__item")
    )

    bucket_totals: dict[int, int] = {}
    for assignment in assignments:
        if assignment.bucket_id is None:
            continue
        duration = durations.get(assignment.user_item_id, 0)
        for bucket in bucket_paths.get(assignment.bucket_id, []):
            bucket_totals[bucket] = bucket_totals.get(bucket, 0) + duration

    candidate_buckets = bucket_children.get(current_bucket_id, [])
    candidate_assignments = [
        assignment
        for assignment in assignments
        if assignment.bucket_id == current_bucket_id
    ]
    candidate_item_ids = {a.user_item_id for a in candidate_assignments}
    eligible_items = {
        item.id: item
        for item in apply_selector_eligibility(
            UserItem.objects.filter(user=request.user, id__in=candidate_item_ids)
        ).select_related("item")
    }

    entries: list[dict[str, object]] = []
    for bucket in candidate_buckets:
        seconds = bucket_totals.get(bucket.id, 0)
        entries.append(
            {
                "kind": "bucket",
                "id": bucket.id,
                "label": bucket.name,
                "seconds": seconds,
                "url": f"{reverse('time_dashboard')}?layout={layout.id}&bucket={bucket.id}",
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
        payload = {
            "id": 0,
            "title": "Nothing to select at this level.",
        }
        response = JsonResponse(payload)
        response["HX-Trigger"] = json.dumps({"action-toast": payload})
        return response

    weights = [1.0 / (entry["seconds"] + 1) for entry in entries]
    chosen = random.choices(entries, weights=weights, k=1)[0]
    payload = {
        "id": int(chosen["id"]),
        "title": str(chosen["label"]),
        "kind": str(chosen["kind"]),
        "url": str(chosen["url"]),
    }
    response = JsonResponse(payload)
    response["HX-Trigger"] = json.dumps({"action-toast": payload})
    return response




@require_POST
@login_required
def time_layout_create(request):
    next_url = request.POST.get("next")
    name = (request.POST.get("layout_name") or "").strip()
    description = (request.POST.get("layout_description") or "").strip()
    if not name:
        messages.error(request, "Layout name is required.")
        return redirect("time_dashboard")

    try:
        layout = TimeLayout.objects.create(
            user=request.user, name=name, description=description
        )
    except IntegrityError:
        messages.error(request, "Layout name already exists.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("time_dashboard")

    messages.success(request, "Layout created.")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(f"{reverse('time_settings')}?layout={layout.id}")
    return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")


@require_POST
@login_required
def time_layout_update(request):
    next_url = request.POST.get("next")
    layout_id = request.POST.get("layout_id")
    name = (request.POST.get("layout_name") or "").strip()
    description = (request.POST.get("layout_description") or "").strip()
    if not layout_id:
        messages.error(request, "Layout not found.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("time_dashboard")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    if not name:
        messages.error(request, "Layout name is required.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    layout.name = name
    layout.description = description
    try:
        layout.save(update_fields=["name", "description"])
    except IntegrityError:
        messages.error(request, "Layout name already exists.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    messages.success(request, "Layout updated.")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")


@require_POST
@login_required
def time_layout_delete(request):
    next_url = request.POST.get("next")
    layout_id = request.POST.get("layout_id")
    if not layout_id:
        messages.error(request, "Layout not found.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("time_dashboard")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    layout.delete()
    messages.success(request, "Layout deleted.")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("time_dashboard")


@require_POST
@login_required
def time_bucket_create(request):
    next_url = request.POST.get("next")
    layout_id = request.POST.get("layout_id")
    name = (request.POST.get("bucket_name") or "").strip()
    parent_id = request.POST.get("parent_id") or None
    if not layout_id:
        messages.error(request, "Layout not found.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("time_dashboard")
    if not name:
        messages.error(request, "Bucket name is required.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("time_dashboard")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    parent = None
    if parent_id:
        parent = get_object_or_404(TimeBucket, id=parent_id, layout=layout)

    try:
        TimeBucket.objects.create(layout=layout, name=name, parent=parent)
    except IntegrityError:
        messages.error(request, "Bucket name already exists under that parent.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    messages.success(request, "Bucket created.")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")


@require_POST
@login_required
def time_bucket_update(request):
    next_url = request.POST.get("next")
    layout_id = request.POST.get("layout_id")
    bucket_id = request.POST.get("bucket_id")
    name = (request.POST.get("bucket_name") or "").strip()
    parent_id = request.POST.get("parent_id") or None
    if not layout_id or not bucket_id:
        messages.error(request, "Bucket not found.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("time_dashboard")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    bucket = get_object_or_404(TimeBucket, id=bucket_id, layout=layout)
    if not name:
        messages.error(request, "Bucket name is required.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    parent = None
    if parent_id:
        parent = get_object_or_404(TimeBucket, id=parent_id, layout=layout)

    if parent is not None and parent.id == bucket.id:
        messages.error(request, "Bucket cannot be its own parent.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    buckets = list(TimeBucket.objects.filter(layout=layout).select_related("parent"))
    descendants = build_bucket_descendants(buckets)
    if parent is not None and parent.id in descendants.get(bucket.id, set()):
        messages.error(request, "Bucket cannot be moved under its descendant.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    bucket.name = name
    bucket.parent = parent
    try:
        bucket.save(update_fields=["name", "parent"])
    except IntegrityError:
        messages.error(request, "Bucket name already exists under that parent.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    messages.success(request, "Bucket updated.")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")


@require_POST
@login_required
def time_bucket_delete(request):
    next_url = request.POST.get("next")
    layout_id = request.POST.get("layout_id")
    bucket_id = request.POST.get("bucket_id")
    delete_mode = request.POST.get("delete_mode") or "promote"
    if not layout_id or not bucket_id:
        messages.error(request, "Bucket not found.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("time_dashboard")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    bucket = get_object_or_404(TimeBucket, id=bucket_id, layout=layout)

    if delete_mode not in {"promote", "cascade"}:
        messages.error(request, "Delete mode is invalid.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    if delete_mode == "cascade":
        bucket.delete()
        messages.success(request, "Bucket and its children deleted.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    with transaction.atomic():
        TimeBucket.objects.filter(layout=layout, parent=bucket).update(
            parent=bucket.parent
        )
        bucket.delete()

    messages.success(request, "Bucket deleted and children promoted.")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")


@require_POST
@login_required
def time_assignment_update(request):
    layout_id = request.POST.get("layout_id")
    item_id = request.POST.get("item_id")
    action = request.POST.get("action")
    next_url = request.POST.get("next")
    if not layout_id or not item_id or not action:
        return redirect("time_dashboard")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    user_item = get_object_or_404(UserItem, id=item_id, user=request.user)
    assignment, _ = TimeBucketAssignment.objects.get_or_create(
        layout=layout, user_item=user_item
    )

    def response_redirect():
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    if action == "ignore":
        assignment.is_ignored = True
        assignment.bucket = None
        assignment.save(update_fields=["is_ignored", "bucket", "updated_at"])
        return response_redirect()

    if action == "unignore":
        assignment.is_ignored = False
        assignment.bucket = None
        assignment.save(update_fields=["is_ignored", "bucket", "updated_at"])
        return response_redirect()

    if action == "unassign":
        assignment.is_ignored = False
        assignment.bucket = None
        assignment.save(update_fields=["is_ignored", "bucket", "updated_at"])
        return response_redirect()

    if action == "assign":
        bucket_id = request.POST.get("bucket_id")
        if not bucket_id:
            return response_redirect()
        bucket = get_object_or_404(TimeBucket, id=bucket_id, layout=layout)
        assignment.bucket = bucket
        assignment.is_ignored = False
        assignment.save(update_fields=["bucket", "is_ignored", "updated_at"])
        return response_redirect()

    return response_redirect()


# unified executor for all actions
@require_POST
@login_required
def useritem_execute_action(request):
    """
    HTMX endpoint.

    Expects POST keys:
        action_slug - slug of the registered action
        selected_ids - optional list[] of UserItem PKs (checkboxes)
        ...parameters... - anything required by the action's ParamForm

    Returns:
        JSON payload produced by the action.
        Header HX-Trigger: "action-toast" (handled by the client JS)
    """
    print(
        "ACTION DEBUG:",
        "method=",
        request.method,
        "path=",
        request.get_full_path(),
        "GET=",
        dict(request.GET),
        "POST_keys=",
        list(request.POST.keys()),
        "POST_filter=",
        request.POST.get("filter"),
        file=sys.stderr,
        flush=True,
    )
    # figure out the action to perform
    slug: str | None = request.POST.get("action_slug")
    if not slug:
        return HttpResponseBadRequest("Missing action slug")

    action: Action | None = action_registry.get(slug)
    if action is None:
        return HttpResponseBadRequest("Unknown action")

    # figure out the queryset
    sel_ids: list[str] = request.POST.getlist("selected_ids")
    if sel_ids:
        qs = UserItem.objects.filter(pk__in=sel_ids, user=request.user)
    else:
        qs = build_useritem_queryset(request)

    # validate action parameters
    try:
        form = action.ParamForm(request.POST, user=request.user)
    except TypeError:
        form = action.ParamForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_json())

    # run action and respond
    payload = action()(qs, user=request.user, **form.cleaned_data)
    response = JsonResponse(payload)
    response["HX-Trigger"] = json.dumps({"action-toast": payload})

    return response


# action bar views ------------------------------------------------------------


@login_required
def list_actions(request):
    """Return <option> list for a given group."""
    group = request.GET.get("action_group")
    actions = [a for a in action_registry.values() if a.group == group]

    return render(
        request,
        "tracker/partials/_action_select.html",
        {"actions": actions},
    )


@login_required
def action_params(request):
    """Return the ParamForm fragment for a given action slug."""
    slug = request.GET.get("action_slug") or ""
    action = action_registry.get(slug)

    if not slug or action is None:
        # return a minimal html so it actually replaces whatever is in position
        return HttpResponse("<span></span>")

    try:
        form = action.ParamForm(auto_id="id_param_%s", user=request.user)
    except TypeError:
        form = action.ParamForm(auto_id="id_param_%s")

    return render(
        request,
        "tracker/partials/_action_params.html",
        {"form": form},
    )
