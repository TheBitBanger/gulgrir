from __future__ import annotations

from typing import Any, ClassVar

from django import forms
from django.db.models import QuerySet

from tracker.actions import ToastPayload, register
from tracker.models import (
    TimeBucket,
    TimeBucketAssignment,
    TimeLayout,
    UserItem,
    UserItemHistory,
)


class _NoParams(forms.Form):
    """Bulk actions need no extra parameters."""


class BulkAssignToBucketForm(forms.Form):
    layout = forms.ModelChoiceField(queryset=TimeLayout.objects.none())
    bucket = forms.ModelChoiceField(queryset=TimeBucket.objects.none())

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is None:
            self.fields["layout"].queryset = TimeLayout.objects.none()
            self.fields["bucket"].queryset = TimeBucket.objects.none()
            return

        self.fields["layout"].queryset = TimeLayout.objects.filter(user=user).order_by(
            "order", "name"
        )
        self.fields["bucket"].queryset = TimeBucket.objects.filter(
            layout__user=user
        ).select_related("layout")

    def clean(self):
        cleaned = super().clean()
        layout = cleaned.get("layout")
        bucket = cleaned.get("bucket")
        if layout and bucket and bucket.layout_id != layout.id:
            self.add_error("bucket", "Bucket does not belong to that layout.")
        return cleaned


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


@register
class BulkAssignToBucket:
    slug: ClassVar[str] = "bulk_assign_to_bucket"
    label: ClassVar[str] = "Assign to bucket"
    group: ClassVar[str] = "bulk"
    ParamForm: ClassVar[type[forms.Form]] = BulkAssignToBucketForm

    def __call__(self, qs: QuerySet[UserItem], **params: Any) -> ToastPayload:  # type: ignore[override]
        layout: TimeLayout = params["layout"]
        bucket: TimeBucket = params["bucket"]
        updated = 0

        for item in qs:
            assignment, _ = TimeBucketAssignment.objects.get_or_create(
                layout=layout,
                user_item=item,
            )
            assignment.bucket = bucket
            assignment.is_ignored = False
            assignment.save(update_fields=["bucket", "is_ignored", "updated_at"])
            updated += 1

        return {
            "title": f"Assigned {updated} item(s) to {bucket.name}",
            "id": 0,
        }
