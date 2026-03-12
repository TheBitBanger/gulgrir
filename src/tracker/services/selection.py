from __future__ import annotations

from django.db.models import OuterRef, Q, QuerySet, Subquery

from tracker.models import UserItem, UserItemHistory


def apply_selector_eligibility(qs: QuerySet[UserItem]) -> QuerySet[UserItem]:
    latest_completed = (
        UserItemHistory.objects.filter(
            user_item=OuterRef("pk"), event_type=UserItemHistory.Event.COMPLETED
        )
        .order_by("-happened_at")
        .values("happened_at")[:1]
    )
    qs = qs.annotate(last_completed_at=Subquery(latest_completed))
    return qs.filter(
        Q(last_completed_at__isnull=True) | Q(is_redoing=True) | Q(is_endless=True)
    )
