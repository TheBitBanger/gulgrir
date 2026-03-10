import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
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


def format_seconds(total_seconds: int) -> str:
    if total_seconds <= 0:
        return "00:00:00"
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def day_range(day: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    end = start + timedelta(days=1)
    return start, end


def load_item_durations(user, start: datetime | None, end: datetime | None) -> dict[int, int]:
    qs = UserItemHistory.objects.filter(
        user_item__user=user,
        event_type=UserItemHistory.Event.REVISITED,
        duration__isnull=False,
        ended_at__isnull=False,
    )
    if start is not None:
        qs = qs.filter(ended_at__gte=start)
    if end is not None:
        qs = qs.filter(ended_at__lt=end)

    durations: dict[int, int] = {}
    for row in qs.values("user_item_id").annotate(total=Sum("duration")):
        total = row["total"]
        if total is None:
            continue
        durations[int(row["user_item_id"])] = int(total.total_seconds())

    return durations


def build_bucket_paths(buckets: list[TimeBucket]) -> dict[int, list[int]]:
    parent_map = {bucket.id: bucket.parent_id for bucket in buckets}
    paths: dict[int, list[int]] = {}

    def path_for(bucket_id: int) -> list[int]:
        if bucket_id in paths:
            return paths[bucket_id]
        path = [bucket_id]
        current = bucket_id
        while parent_map.get(current):
            parent = parent_map[current]
            path.append(parent)
            current = parent
        paths[bucket_id] = path
        return path

    for bucket in buckets:
        if bucket.id is not None:
            path_for(bucket.id)

    return paths


def build_chart_entries(
    *,
    layout: TimeLayout,
    buckets: list[TimeBucket],
    assignments: dict[int, TimeBucketAssignment],
    item_durations: dict[int, int],
    user_items: dict[int, UserItem],
    bucket_id: int | None,
    top_n: int,
) -> dict[str, object]:
    bucket_by_id = {bucket.id: bucket for bucket in buckets}
    bucket_children: dict[int | None, list[TimeBucket]] = defaultdict(list)
    for bucket in buckets:
        bucket_children[bucket.parent_id].append(bucket)
    for child_list in bucket_children.values():
        child_list.sort(key=lambda b: (b.order, b.name.lower()))

    parent_map = {bucket.id: bucket.parent_id for bucket in buckets}

    def top_bucket_id(bucket_id: int) -> int:
        current = bucket_id
        while parent_map.get(current):
            current = parent_map[current]
        return current

    def path_to_root(bucket_id: int) -> list[int]:
        path = [bucket_id]
        current = bucket_id
        while parent_map.get(current):
            current = parent_map[current]
            path.append(current)
        return path

    selected_bucket = None
    if bucket_id is not None:
        selected_bucket = bucket_by_id.get(bucket_id)

    level_buckets = bucket_children.get(None, [])
    if selected_bucket is not None:
        level_buckets = bucket_children.get(selected_bucket.id, [])

    bucket_totals: dict[int | str, int] = defaultdict(int)
    unassigned_items: list[dict[str, object]] = []
    ignored_items: list[dict[str, object]] = []
    leaf_items: list[dict[str, object]] = []
    direct_items: list[dict[str, object]] = []

    for item_id, item in user_items.items():
        seconds = item_durations.get(item_id, 0)
        assignment = assignments.get(item_id)
        if assignment and assignment.is_ignored:
            ignored_items.append(
                {
                    "item": item,
                    "seconds": seconds,
                    "duration_display": format_seconds(seconds),
                }
            )
            continue

        if assignment and assignment.bucket_id:
            assigned_bucket_id = assignment.bucket_id
            if selected_bucket is None:
                bucket_totals[top_bucket_id(assigned_bucket_id)] += seconds
            else:
                path = path_to_root(assigned_bucket_id)
                if selected_bucket.id in path:
                    if level_buckets:
                        if assigned_bucket_id == selected_bucket.id:
                            direct_items.append(
                                {
                                    "item": item,
                                    "seconds": seconds,
                                    "duration_display": format_seconds(seconds),
                                }
                            )
                        else:
                            idx = path.index(selected_bucket.id)
                            if idx > 0:
                                child_id = path[idx - 1]
                                bucket_totals[child_id] += seconds
                    else:
                        leaf_items.append(
                            {
                                "item": item,
                                "seconds": seconds,
                                "duration_display": format_seconds(seconds),
                            }
                        )
            continue

        if selected_bucket is None and seconds > 0:
            unassigned_items.append(
                {
                    "item": item,
                    "seconds": seconds,
                    "duration_display": format_seconds(seconds),
                }
            )

    bucket_entries = []
    for bucket in level_buckets:
        bucket_entries.append(
            {
                "label": bucket.name,
                "seconds": bucket_totals.get(bucket.id, 0),
                "kind": "bucket",
                "bucket_id": bucket.id,
            }
        )
    bucket_entries = sorted(bucket_entries, key=lambda x: x["seconds"], reverse=True)

    item_entries = []
    if selected_bucket is None:
        for row in unassigned_items:
            item_entries.append(
                {
                    "label": row["item"].display_title,
                    "seconds": row["seconds"],
                    "kind": "item",
                    "item_id": row["item"].id,
                }
            )
        item_entries = sorted(item_entries, key=lambda x: x["seconds"], reverse=True)
    elif selected_bucket is not None and not level_buckets:
        for row in leaf_items:
            item_entries.append(
                {
                    "label": row["item"].display_title,
                    "seconds": row["seconds"],
                    "kind": "item",
                    "item_id": row["item"].id,
                }
            )
        item_entries = sorted(item_entries, key=lambda x: x["seconds"], reverse=True)
    elif selected_bucket is not None and level_buckets:
        for row in direct_items:
            item_entries.append(
                {
                    "label": row["item"].display_title,
                    "seconds": row["seconds"],
                    "kind": "item",
                    "item_id": row["item"].id,
                }
            )
        item_entries = sorted(item_entries, key=lambda x: x["seconds"], reverse=True)

    selected = bucket_entries[:top_n]
    remaining_slots = max(0, top_n - len(selected))
    selected_items = item_entries[:remaining_slots]

    overflow_seconds = sum(x["seconds"] for x in bucket_entries[top_n:])
    overflow_seconds += sum(x["seconds"] for x in item_entries[remaining_slots:])

    entries = selected + selected_items
    if overflow_seconds > 0:
        entries.append(
            {
                "label": "Others",
                "seconds": overflow_seconds,
                "kind": "overflow",
            }
        )

    max_seconds = max((entry["seconds"] for entry in entries), default=0)
    for entry in entries:
        if max_seconds > 0:
            entry["percent"] = round(entry["seconds"] / max_seconds * 100, 2)
        else:
            entry["percent"] = 0
        entry["duration_display"] = format_seconds(entry["seconds"])

    ignored_items = sorted(ignored_items, key=lambda x: x["seconds"], reverse=True)
    unassigned_items = sorted(unassigned_items, key=lambda x: x["seconds"], reverse=True)

    return {
        "entries": entries,
        "total_seconds": sum(item_durations.values()),
        "total_display": format_seconds(sum(item_durations.values())),
        "unassigned_items": unassigned_items,
        "ignored_items": ignored_items,
        "selected_bucket": selected_bucket,
    }


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
        return super().form_valid(form)

    # Helper methods for tag pill selector
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

        user_item = self.object
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

        return ctx

    def get_success_url(self):
        return reverse("useritem_detail", kwargs={"pk": self.object.pk})


class UserItemDelete(OwnObjectsMixin, DeleteView):
    model = UserItem
    success_url = reverse_lazy("useritem_dashboard")
    template_name = "tracker/confirm_delete.html"


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

    if layout:
        now = timezone.now()
        today = timezone.localdate()
        day_before = today - timedelta(days=2)
        yesterday = today - timedelta(days=1)

        def period_context(start: datetime | None, end: datetime | None, label: str):
            durations = load_item_durations(request.user, start, end)
            chart = build_chart_entries(
                layout=layout,
                buckets=buckets,
                assignments=assignments,
                item_durations=durations,
                user_items=user_items,
                bucket_id=bucket_id,
                top_n=10,
            )
            chart["label"] = label
            return chart

        for day, label in [
            (today, "Today"),
            (yesterday, "Yesterday"),
            (day_before, "Day before"),
        ]:
            start, end = day_range(day)
            daily_contexts.append(period_context(start, end, label))

        for days, label in [
            (7, "Last 7 days"),
            (30, "Last 30 days"),
            (365, "Last 365 days"),
        ]:
            start = now - timedelta(days=days)
            rolling_contexts.append(period_context(start, now, label))

        all_time_context = period_context(None, None, "All time")

        all_time_assignments = build_chart_entries(
            layout=layout,
            buckets=buckets,
            assignments=assignments,
            item_durations=load_item_durations(request.user, None, None),
            user_items=user_items,
            bucket_id=None,
            top_n=10,
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
        breadcrumb_buckets = [bucket_by_id[b_id] for b_id in path_ids if b_id in bucket_by_id]

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
        },
    )


def build_bucket_option_list(buckets: list[TimeBucket]) -> list[dict[str, object]]:
    bucket_children: dict[int | None, list[TimeBucket]] = defaultdict(list)
    for bucket in buckets:
        bucket_children[bucket.parent_id].append(bucket)
    for child_list in bucket_children.values():
        child_list.sort(key=lambda b: (b.order, b.name.lower()))

    options: list[dict[str, object]] = []

    def walk(parent_id: int | None, depth: int):
        for bucket in bucket_children.get(parent_id, []):
            prefix = "--" * depth
            label = f"{prefix} {bucket.name}".strip()
            options.append({"id": bucket.id, "label": label})
            walk(bucket.id, depth + 1)

    walk(None, 0)
    return options


@require_POST
@login_required
def time_layout_create(request):
    name = (request.POST.get("layout_name") or "").strip()
    description = (request.POST.get("layout_description") or "").strip()
    if not name:
        return redirect("time_dashboard")

    TimeLayout.objects.create(user=request.user, name=name, description=description)
    return redirect("time_dashboard")


@require_POST
@login_required
def time_bucket_create(request):
    layout_id = request.POST.get("layout_id")
    name = (request.POST.get("bucket_name") or "").strip()
    parent_id = request.POST.get("parent_id") or None
    if not layout_id or not name:
        return redirect("time_dashboard")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    parent = None
    if parent_id:
        parent = get_object_or_404(TimeBucket, id=parent_id, layout=layout)

    TimeBucket.objects.create(layout=layout, name=name, parent=parent)
    return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")


@require_POST
@login_required
def time_assignment_update(request):
    layout_id = request.POST.get("layout_id")
    item_id = request.POST.get("item_id")
    action = request.POST.get("action")
    if not layout_id or not item_id or not action:
        return redirect("time_dashboard")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    user_item = get_object_or_404(UserItem, id=item_id, user=request.user)
    assignment, _ = TimeBucketAssignment.objects.get_or_create(
        layout=layout, user_item=user_item
    )

    if action == "ignore":
        assignment.is_ignored = True
        assignment.bucket = None
        assignment.save(update_fields=["is_ignored", "bucket", "updated_at"])
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    if action == "unignore":
        assignment.is_ignored = False
        assignment.bucket = None
        assignment.save(update_fields=["is_ignored", "bucket", "updated_at"])
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    if action == "assign":
        bucket_id = request.POST.get("bucket_id")
        if not bucket_id:
            return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")
        bucket = get_object_or_404(TimeBucket, id=bucket_id, layout=layout)
        assignment.bucket = bucket
        assignment.is_ignored = False
        assignment.save(update_fields=["bucket", "is_ignored", "updated_at"])
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")


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
    form = action.ParamForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_json())

    # run action and respond
    payload = action()(qs, **form.cleaned_data)
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

    form = action.ParamForm(auto_id="id_param_%s")

    return render(
        request,
        "tracker/partials/_action_params.html",
        {"form": form},
    )
