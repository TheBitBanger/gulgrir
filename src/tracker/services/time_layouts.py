from __future__ import annotations

from ..models import Profile, TimeLayout


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

    if persist_default and profile and profile.time_default_layout_id != resolved_layout.id:
        profile.time_default_layout = resolved_layout
        profile.save(update_fields=["time_default_layout"])

    return layouts, resolved_layout
