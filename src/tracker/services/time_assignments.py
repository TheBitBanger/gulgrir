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
    assignment.assignment_mode = TimeBucketAssignment.Mode.BUCKET
    assignment.save(update_fields=["bucket", "assignment_mode", "updated_at"])


def assign_item_to_top_level(layout: TimeLayout, user_item: UserItem) -> None:
    assignment = _get_assignment(layout, user_item)
    assignment.bucket = None
    assignment.assignment_mode = TimeBucketAssignment.Mode.TOP_LEVEL
    assignment.save(update_fields=["bucket", "assignment_mode", "updated_at"])


def unassign_item(layout: TimeLayout, user_item: UserItem) -> None:
    TimeBucketAssignment.objects.filter(layout=layout, user_item=user_item).delete()


def ignore_item(layout: TimeLayout, user_item: UserItem) -> None:
    assignment = _get_assignment(layout, user_item)
    assignment.assignment_mode = TimeBucketAssignment.Mode.IGNORED
    assignment.bucket = None
    assignment.save(update_fields=["assignment_mode", "bucket", "updated_at"])


def unignore_item(layout: TimeLayout, user_item: UserItem) -> None:
    TimeBucketAssignment.objects.filter(layout=layout, user_item=user_item).delete()
