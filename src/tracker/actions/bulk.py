from __future__ import annotations

from typing import Any, ClassVar

from django import forms
from django.db.models import QuerySet

from tracker.actions import ToastPayload, register
from tracker.models import UserItem, UserItemHistory


class _NoParams(forms.Form):
    """Bulk actions need no extra parameters."""


@register
class BulkMarkCompleted:
    slug: ClassVar[str] = "bulk_mark_completed"
    label: ClassVar[str] = "Mark Completed"
    group: ClassVar[str] = "bulk"
    ParamForm: ClassVar[type[forms.Form]] = _NoParams

    def __call__(self, qs: QuerySet[UserItem], **params: Any) -> ToastPayload:  # type: ignore[override]
        n = qs.record_event(UserItemHistory.Event.COMPLETED)

        return {"title": f"Completed {n} item(s)", "id": 0}


@register
class BulkMarkRevisited:
    slug: ClassVar[str] = "bulk_mark_revisited"
    label: ClassVar[str] = "Mark Revisited"
    group: ClassVar[str] = "bulk"
    ParamForm: ClassVar[type[forms.Form]] = _NoParams

    def __call__(self, qs: QuerySet[UserItem], **params: Any) -> ToastPayload:  # type: ignore[override]
        n = qs.record_event(UserItemHistory.Event.REVISITED)

        return {"title": f"Revisited {n} item(s)", "id": 0}
