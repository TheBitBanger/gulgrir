from __future__ import annotations
from datetime import timedelta

import random
from typing import Any, ClassVar

from django import forms
from django.db.models import (
    DurationField,
    ExpressionWrapper,
    F,
    OuterRef,
    QuerySet,
    Subquery,
    DateTimeField,
    Value,
)
from django.db.models.functions import Now, Coalesce
from django.utils import timezone

from tracker.models import UserItem, UserItemHistory
from . import register, ToastPayload


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
        weights = [max(obj.age.total_seconds(), 1.0) for obj in items]
        chosen = random.choices(items, weights=weights, k=1)[0]

        # Must match ToastPayload TypedDict (id + title)
        return {"id": chosen.pk, "title": chosen.display_title}
