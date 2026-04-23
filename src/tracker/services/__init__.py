from typing import Any

from django.db.models import QuerySet
from django.http import HttpRequest

from ..forms import UserItemFilterForm
from ..models import SavedFilter, UserItem


def build_useritem_queryset(request: HttpRequest) -> QuerySet[UserItem]:
    """
    Build the filtered queryset for the UserItem dashboard
    """

    # Always treat URL as the dataset state, but allow POST
    # to carry or override it for actions.
    data = request.GET.copy()
    if request.method == "POST":
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

    data.pop("sf", None)

    form = UserItemFilterForm(data, user=request.user)
    if form.is_valid():
        data_def = form.to_definition()
        if data_def:
            definition.update(data_def)

    q_obj = SavedFilter(user=request.user, definition=definition).as_q()

    return (
        UserItem.objects.filter(q_obj, user=request.user)
        .prefetch_related("tags", "item")
        .with_latest_dates()
        .order_by("last_revisited_at")
    )
