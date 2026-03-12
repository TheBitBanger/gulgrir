from __future__ import annotations

from django.utils import timezone

from ..models import UserItem, UserItemHistory


def can_restart(user_item: UserItem) -> bool:
    if user_item.is_redoing:
        return False
    return user_item.history.filter(
        event_type=UserItemHistory.Event.COMPLETED
    ).exists()


def mark_completed(user_item: UserItem) -> None:
    UserItemHistory.objects.create(
        user_item=user_item,
        event_type=UserItemHistory.Event.COMPLETED,
        happened_at=timezone.now(),
    )
    user_item.shelf = UserItem.Shelf.DONE
    user_item.is_redoing = False
    user_item.save(update_fields=["shelf", "is_redoing"])


def restart_item(user_item: UserItem) -> None:
    if not can_restart(user_item):
        raise ValueError("Item cannot be restarted yet.")
    user_item.is_redoing = True
    user_item.shelf = UserItem.Shelf.IN_PROGRESS
    user_item.save(update_fields=["is_redoing", "shelf"])
