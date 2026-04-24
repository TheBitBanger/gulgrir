from __future__ import annotations

import random
from datetime import timedelta
from typing import Any, ClassVar, Protocol, cast

from django import forms
from django.db.models import (
    DateTimeField,
    DurationField,
    ExpressionWrapper,
    F,
    OuterRef,
    QuerySet,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce, Now
from django.urls import reverse
from django.utils import timezone

from tracker.models import UserItem, UserItemHistory
from tracker.services.selection import apply_selector_eligibility
from tracker.services.time_dashboard import load_item_durations
from tracker.services.time_windows import find_time_window, time_window_choices

from . import ToastPayload, register


class _WeightedItem(Protocol):
    age: timedelta


class RandomWeightedForm(forms.Form):
    WEIGHT_CHOICES = (
        ("last_revisited_at", "Older 'last revisited' ↑"),
        ("created_at", "Older 'created' ↑"),
    )
    weight_column = forms.ChoiceField(
        choices=WEIGHT_CHOICES,
        label="Weight column",
        initial="last_revisited_at",
    )


class RandomWeightedTimeForm(forms.Form):
    time_window = forms.ChoiceField(
        choices=(),
        label="Time window",
        initial="all_time",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        time_window_field = cast(forms.ChoiceField, self.fields["time_window"])
        time_window_field.choices = time_window_choices()


@register
class RandomWeightedSelector:
    """
    Pick **one** item from the queryset with probability proportional to age.

    Older timestamps ⇒ larger weight ⇒ more likely to be chosen.
    """

    slug: ClassVar[str] = "random_weighted"  # machine-friendly
    label: ClassVar[str] = "Random weighted"  # human-friendly (2nd dropdown)
    group: ClassVar[str] = "selector"  # 1st dropdown
    ParamForm: ClassVar[type[forms.Form]] = (
        RandomWeightedForm  # for the dynamic param UI
    )

    def __call__(
        self,
        qs: QuerySet[UserItem],
        **params: Any,  # cleaned data from ParamForm
    ) -> ToastPayload:
        field: str = params.get("weight_column", "last_revisited_at")
        qs = apply_selector_eligibility(qs)

        # For non-existent dates choose a very old one
        ancient = timezone.now() - timedelta(days=365 * 20)  # 20 years ago

        # provide "last_revisited_at" on-the-fly via a subquery
        if field == "last_revisited_at":
            # latest "revisited" event per UserItem
            latest = (
                UserItemHistory.objects.filter(
                    user_item=OuterRef("pk"), event_type="revisited"
                )
                .order_by("-happened_at")
                .values("happened_at")[:1]
            )
            qs = qs.annotate(last_revisited_at=Subquery(latest))

        # Annotate each row with an "age" duration, coalesce NULLs to an "ancient" value
        effective_field = f"effective_{field}"
        qs = qs.annotate(
            **{
                effective_field: Coalesce(
                    F(field), Value(ancient, output_field=DateTimeField())
                )
            }
        ).annotate(
            age=ExpressionWrapper(
                Now() - F(effective_field), output_field=DurationField()
            )
        )

        items = list(qs)
        if not items:  # guard against empty queryset
            raise ValueError("Empty queryset passed to RandomWeightedSelector")

        # Convert duration to positive float seconds for random.choices
        weighted_items = cast(list[_WeightedItem], items)
        weights = [max(obj.age.total_seconds(), 1.0) for obj in weighted_items]
        # Feature-level weighted selection; cryptographic randomness is not required.
        chosen = random.choices(items, weights=weights, k=1)[0]  # nosec B311

        # Must match ToastPayload TypedDict (id + title)
        return {
            "id": chosen.pk,
            "title": chosen.display_title,
            "kind": "item",
            "url": reverse("useritem_detail", kwargs={"pk": chosen.pk}),
        }


@register
class RandomWeightedTimeSelector:
    """
    Pick **one** item from the queryset with probability proportional to time spent.

    Lower time ⇒ larger weight ⇒ more likely to be chosen.
    """

    slug: ClassVar[str] = "random_weighted_time"
    label: ClassVar[str] = "Random weighted (time)"
    group: ClassVar[str] = "selector"
    ParamForm: ClassVar[type[forms.Form]] = RandomWeightedTimeForm

    def __call__(
        self,
        qs: QuerySet[UserItem],
        **params: Any,
    ) -> ToastPayload:
        qs = apply_selector_eligibility(qs)
        items = list(qs)
        if not items:
            raise ValueError("Empty queryset passed to RandomWeightedTimeSelector")

        window = find_time_window(params.get("time_window"))
        start = window.start if window else None
        end = window.end if window else None
        user = params.get("user")
        if user is None:
            raise ValueError("User is required for time-weighted selection")

        durations = load_item_durations(user, start, end)
        weights = [1.0 / (durations.get(item.id, 0) + 1) for item in items]
        # Feature-level weighted selection; cryptographic randomness is not required.
        chosen = random.choices(items, weights=weights, k=1)[0]  # nosec B311

        return {
            "id": chosen.pk,
            "title": chosen.display_title,
            "kind": "item",
            "url": reverse("useritem_detail", kwargs={"pk": chosen.pk}),
        }
