import json
import re
import sys
from datetime import date, datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
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
from .models import Item, Profile, SavedFilter, Tag, UserItem, UserItemHistory
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
