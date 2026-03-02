from typing import Any
import sys

from django.db.models import QuerySet
from django.http import HttpRequest, QueryDict

from .forms import UserItemFilterForm
from .models import SavedFilter, UserItem


def build_useritem_queryset(request: HttpRequest) -> QuerySet[UserItem]:
    """
    Build the filtered queryset for the UserItem dashboard
    """

    # Always treat URL as the dataset state, but allow POST to carry/override it for actions
    data = request.GET.copy()
    if request.method == "POST":
        # replaced with the snippet below
        # data.update(request.POST)

        for key in request.POST.keys():
            values = request.POST.getlist(key)
            if not values:
                continue
            if all(v == "" for v in values):
                continue
            data.setlist(key, values)

    # Remove action-only keys so they don't interfere with the filter form
    for k in (
        "action_group",
        "action_slug",
        "weight_column",
        "selected_ids",
        "csrfmiddlewaretoken",
    ):
        data.pop(k, None)

    definition: dict[str, Any] = {}

    # 1) Base layer: SavedFilter (if any)
    filter_id = data.get("filter")
    if filter_id:
        sf = SavedFilter.objects.filter(pk=filter_id, user=request.user).first()
        if sf and sf.definition:
            definition.update(sf.definition)

    # 2) Overlay: explicit filter-bar controls
    form = UserItemFilterForm(data, user=request.user)
    if form.is_valid():
        data_def = form.to_definition()
        if data_def:
            definition.update(data_def)

    q_obj = SavedFilter(user=request.user, definition=definition).as_q()

    print(
        "QS DEBUG:",
        "method=",
        request.method,
        "GET_filter=",
        request.GET.get("filter"),
        "data_filter=",
        data.get("filter"),
        "definition=",
        definition,
        "q_obj=",
        q_obj,
        file=sys.stderr,
        flush=True,
    )

    return (
        UserItem.objects.filter(q_obj, user=request.user)
        .prefetch_related("tags", "item")
        .with_latest_dates()
        .order_by("last_revisited_at")
    )
