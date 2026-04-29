from __future__ import annotations

from ..models import Profile, TimeBucket, TimeBucketAssignment, TimeLayout


def resolve_default_layout(
    *,
    user,
    requested_layout_id: str | int | None = None,
    profile: Profile | None = None,
    persist_default: bool = False,
) -> tuple[list[TimeLayout], TimeLayout | None]:
    layouts = list(TimeLayout.objects.filter(user=user).order_by("order", "name"))
    if not layouts:
        if persist_default and profile and profile.time_default_layout_id is not None:
            profile.time_default_layout = None
            profile.save(update_fields=["time_default_layout"])
        return [], None

    layout_by_id = {layout.id: layout for layout in layouts}
    resolved_layout: TimeLayout | None = None

    selected_id: int | None = None
    if requested_layout_id is not None and requested_layout_id != "":
        try:
            selected_id = int(requested_layout_id)
        except (TypeError, ValueError):
            selected_id = None

    if selected_id is not None:
        resolved_layout = layout_by_id.get(selected_id)

    if resolved_layout is None and profile:
        default_id = profile.time_default_layout_id
        if default_id is not None:
            resolved_layout = layout_by_id.get(default_id)

    if resolved_layout is None:
        resolved_layout = layouts[0]

    if (
        persist_default
        and profile
        and profile.time_default_layout_id != resolved_layout.id
    ):
        profile.time_default_layout = resolved_layout
        profile.save(update_fields=["time_default_layout"])

    return layouts, resolved_layout


def build_assignment_labels_for_items(
    *,
    layout: TimeLayout | None,
    item_ids: set[int],
) -> dict[int, str]:
    if layout is None or not item_ids:
        return {}

    assignments = list(
        TimeBucketAssignment.objects.filter(
            layout=layout,
            user_item_id__in=item_ids,
        ).select_related("bucket", "bucket__parent")
    )

    bucket_ids = {
        assignment.bucket_id
        for assignment in assignments
        if assignment.assignment_mode == TimeBucketAssignment.Mode.BUCKET
        and assignment.bucket_id is not None
    }
    bucket_by_id = {
        bucket.id: bucket
        for bucket in TimeBucket.objects.filter(
            layout=layout,
            id__in=bucket_ids,
        ).select_related("parent")
    }

    def bucket_path_label(bucket_id: int) -> str:
        names: list[str] = []
        current_bucket = bucket_by_id.get(bucket_id)
        seen: set[int] = set()
        while current_bucket is not None and current_bucket.id not in seen:
            seen.add(current_bucket.id)
            names.append(current_bucket.name)
            parent_id = current_bucket.parent_id
            current_bucket = (
                bucket_by_id.get(parent_id) if parent_id is not None else None
            )
        if not names:
            return "Unassigned"
        return " / ".join(reversed(names))

    labels: dict[int, str] = {}
    for assignment in assignments:
        if assignment.assignment_mode == TimeBucketAssignment.Mode.TOP_LEVEL:
            labels[assignment.user_item_id] = "Top level"
            continue
        if assignment.assignment_mode == TimeBucketAssignment.Mode.BUCKET:
            if assignment.bucket_id is not None:
                labels[assignment.user_item_id] = bucket_path_label(
                    assignment.bucket_id
                )
            else:
                labels[assignment.user_item_id] = "Unassigned"
            continue
        labels[assignment.user_item_id] = "Ignored"

    return labels
