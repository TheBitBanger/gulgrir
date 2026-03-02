import json
import sys

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.http import urlencode
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django.views.generic.list import ListView

from tracker.actions import Action
from tracker.actions import registry as action_registry

from .forms import ProfileForm, UserItemFilterForm, UserItemForm
from .models import Item, Profile, Queue, SavedFilter, Tag, UserItem, UserItemHistory
from .services import build_useritem_queryset


@login_required
def queue_list(request):
    queues = request.user.queues.all()

    return render(request, "tracker/queue_list.html", {"queues": queues})


@login_required
def queue_detail(request, pk):
    queue = get_object_or_404(Queue, pk=pk, user=request.user)
    items = (
        UserItem.objects.filter(queue.as_q())
        .select_related("item")
        .prefetch_related("tags")
        .with_latest_dates()
        .order_by(*queue.ordering_clause())
    )

    return render(
        request,
        "tracker/queue_detail.html",
        {"queue": queue, "items": items},
    )


@login_required
def no_queue(request):
    """All UserItems that do **not** match any of the user's queues."""
    # Build a big OR of every queue filter, the negate
    qs = request.user.queues.all()
    combined_q = Q()
    for q in qs:
        combined_q |= q.as_q()

    items = (
        UserItem.objects.filter(user=request.user)
        .exclude(combined_q)
        .select_related("item")
        .prefetch_related("tags")
        .with_latest_dates()
    )

    return render(request, "tracker/no_queue.html", {"items": items})


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


class ItemList(ListView):
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


class UserItemDelete(OwnObjectsMixin, DeleteView):
    model = UserItem
    success_url = reverse_lazy("useritem_dashboard")
    template_name = "tracker/confirm_delete.html"


class TagCreate(LoginRequiredMixin, CreateView):
    model = Tag
    fields = ["name"]
    template_name = "tracker/form.html"
    success_url = reverse_lazy("tag_list")
    extra_context = {"model_verbose": Tag._meta.verbose_name}

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class TagList(OwnObjectsMixin, ListView):
    model = Tag
    template_name = "tracker/tag_list.html"


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


class QueueCreate(LoginRequiredMixin, CreateView):
    model = Queue
    fields = ["name", "filter_definition", "ordering_definition", "position"]
    template_name = "tracker/form.html"
    success_url = reverse_lazy("queue_manage")
    extra_context = {"model_verbose": Queue._meta.verbose_name}

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class QueueList(OwnObjectsMixin, ListView):
    model = Queue
    template_name = "tracker/queue_manage.html"


class QueueUpdate(OwnObjectsMixin, UpdateView):
    model = Queue
    fields = ["name", "filter_definition", "ordering_definition", "position"]
    template_url = "tracker/form.html"
    success_url = reverse_lazy("queue_manage")


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

    # pass the filter form status to all subsequent requests to restore state
    data = request.GET.copy()
    data.pop("filter", None)
    form = UserItemFilterForm(data, user=request.user)

    items = build_useritem_queryset(request)

    # htmx -------------------------------------------------------------------
    if request.headers.get("HX-Request"):
        target = request.headers.get("HX-Target", "")
        ctx = {
            "form": UserItemFilterForm(request.GET or None, user=request.user),
            "items": items,
            "saved_filters": saved_filters,
        }

        if target == "item-table":
            # normal filtering -> only replace the table
            return render(request, "tracker/partials/useritem_table.html", ctx)
        else:
            # clear button or anything else -> replace filters + table
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

    sf, _created = SavedFilter.objects.update_or_create(
        user=request.user,
        name=name,
        defaults={"definition": form.to_definition()},
    )

    url = f"{reverse('useritem_dashboard')}?{urlencode({'filter': sf.pk})}"
    resp = HttpResponse("")
    resp["HX-Redirect"] = url

    return resp


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
