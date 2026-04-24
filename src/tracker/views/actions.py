import json
import sys
from collections.abc import Callable
from typing import Any, cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AnonymousUser
from django.db.models import QuerySet
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from tracker.actions import Action
from tracker.actions import registry as action_registry

from ..models import UserItem, UserItemHistory
from ..services import build_useritem_queryset


def _get_authenticated_user(request):
    user = request.user
    if isinstance(user, AnonymousUser):
        raise ValueError("Authentication required")
    return user


def _build_param_form(param_form_cls, *args: Any, user, **kwargs: Any):
    build_form = cast(Callable[..., Any], param_form_cls)
    try:
        return build_form(*args, user=user, **kwargs)
    except TypeError:
        return build_form(*args, **kwargs)


@require_POST
@login_required
def bulk_history_action(request):
    """
    Re-usable endpoint that any list template can POST to with:
        action = 'completed' | 'revisited'
        selected_ids = repeated UserItem IDs (e.g. selected_ids=1&selected_ids=2)
    """
    user = _get_authenticated_user(request)

    action = request.POST.get("action")
    ids = request.POST.getlist("selected_ids")

    valid_actions = {
        "completed": UserItemHistory.Event.COMPLETED,
        "revisited": UserItemHistory.Event.REVISITED,
    }
    if action not in valid_actions or not ids:
        return redirect(request.META.get("HTTP_REFERER", "/"))

    queryset = UserItem.objects.filter(user=user, id__in=ids).select_related("item")

    history_records = [
        UserItemHistory(user_item=ui, event_type=valid_actions[action])
        for ui in queryset
    ]
    UserItemHistory.objects.bulk_create(history_records)

    if action == "completed":
        queryset.update(shelf=UserItem.Shelf.DONE)

    return redirect(request.META.get("HTTP_REFERER", "/"))


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
    user = _get_authenticated_user(request)

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
    slug: str | None = request.POST.get("action_slug")
    if not slug:
        return HttpResponseBadRequest("Missing action slug")

    action_cls: type[Action] | None = action_registry.get(slug)
    if action_cls is None:
        return HttpResponseBadRequest("Unknown action")
    action = action_cls()

    sel_ids: list[str] = request.POST.getlist("selected_ids")
    qs: QuerySet[UserItem]
    if sel_ids:
        qs = UserItem.objects.filter(pk__in=sel_ids, user=user)
    else:
        qs = build_useritem_queryset(request)

    form = _build_param_form(action.ParamForm, request.POST, user=user)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_json())

    payload = action(qs, user=user, **form.cleaned_data)
    response = JsonResponse(payload)
    response["HX-Trigger"] = json.dumps({"action-toast": payload})

    return response


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
    user = _get_authenticated_user(request)

    slug = request.GET.get("action_slug") or ""
    action = action_registry.get(slug)

    if not slug or action is None:
        return HttpResponse("<span></span>")

    form = _build_param_form(action.ParamForm, auto_id="id_param_%s", user=user)

    return render(
        request,
        "tracker/partials/_action_params.html",
        {"form": form},
    )
