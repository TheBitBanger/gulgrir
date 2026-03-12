from __future__ import annotations

from ..models import TimeBucket, TimeBucketAssignment, TimeLayout, UserItem


def _get_assignment(layout: TimeLayout, user_item: UserItem) -> TimeBucketAssignment:
    assignment, _ = TimeBucketAssignment.objects.get_or_create(
        layout=layout,
        user_item=user_item,
    )
    return assignment


def assign_item(layout: TimeLayout, user_item: UserItem, bucket: TimeBucket) -> None:
    if bucket.layout_id != layout.id:
        raise ValueError("Bucket does not belong to layout.")
    assignment = _get_assignment(layout, user_item)
    assignment.bucket = bucket
    assignment.is_ignored = False
    assignment.save(update_fields=["bucket", "is_ignored", "updated_at"])


def unassign_item(layout: TimeLayout, user_item: UserItem) -> None:
    assignment = _get_assignment(layout, user_item)
    assignment.bucket = None
    assignment.is_ignored = False
    assignment.save(update_fields=["bucket", "is_ignored", "updated_at"])


def ignore_item(layout: TimeLayout, user_item: UserItem) -> None:
    assignment = _get_assignment(layout, user_item)
    assignment.is_ignored = True
    assignment.bucket = None
    assignment.save(update_fields=["is_ignored", "bucket", "updated_at"])


def unignore_item(layout: TimeLayout, user_item: UserItem) -> None:
    assignment = _get_assignment(layout, user_item)
    assignment.is_ignored = False
    assignment.bucket = None
    assignment.save(update_fields=["is_ignored", "bucket", "updated_at"])
