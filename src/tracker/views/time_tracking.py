import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..models import TimeBucket, TimeBucketAssignment, TimeLayout, UserItem
from ..services.time_assignments import assign_item, ignore_item, unassign_item, unignore_item
from ..services.time_dashboard import (
    build_bucket_children_map,
    build_bucket_descendants,
    build_bucket_option_list,
)
from ..services.time_dashboard_rules import build_dashboard_context_for_user
from ..services.time_selection import select_from_level_for_user


@login_required
def time_dashboard(request):
    layout_id = request.GET.get("layout")
    selected_bucket_id = request.GET.get("bucket")
    bucket_id = int(selected_bucket_id) if selected_bucket_id else None
    show_zero_time = request.GET.get("show_zero") == "1"
    context = build_dashboard_context_for_user(
        user=request.user,
        layout_id=layout_id,
        bucket_id=bucket_id,
        show_zero_time=show_zero_time,
    )
    return render(request, "tracker/time_dashboard.html", context)


@login_required
def time_settings(request):
    layouts = list(
        TimeLayout.objects.filter(user=request.user).order_by("order", "name")
    )
    layout = None
    if layouts:
        layout_id = request.GET.get("layout")
        if layout_id:
            layout = next((l for l in layouts if str(l.id) == layout_id), None)
        layout = layout or layouts[0]

    buckets: list[TimeBucket] = []
    if layout:
        buckets = list(TimeBucket.objects.filter(layout=layout).select_related("parent"))

    bucket_options = []
    bucket_management: list[dict[str, object]] = []
    assigned_items_by_bucket: dict[int, list[TimeBucketAssignment]] = {}
    if layout:
        bucket_options = build_bucket_option_list(buckets)
        bucket_children = build_bucket_children_map(buckets)
        bucket_descendants = build_bucket_descendants(buckets)
        assignments = list(
            TimeBucketAssignment.objects.filter(
                layout=layout,
                bucket__isnull=False,
                is_ignored=False,
            ).select_related("bucket", "user_item__item")
        )
        for assignment in assignments:
            if assignment.bucket_id is None:
                continue
            assigned_items_by_bucket.setdefault(assignment.bucket_id, []).append(
                assignment
            )
        for items in assigned_items_by_bucket.values():
            items.sort(key=lambda row: row.user_item.display_title.lower())

        def build_bucket_management(parent_id: int | None, depth: int) -> None:
            for bucket in bucket_children.get(parent_id, []):
                exclude_ids = {bucket.id} | bucket_descendants.get(bucket.id, set())
                bucket_management.append(
                    {
                        "bucket": bucket,
                        "depth": depth,
                        "has_children": bool(bucket_children.get(bucket.id)),
                        "items": assigned_items_by_bucket.get(bucket.id, []),
                        "parent_options": build_bucket_option_list(
                            buckets, exclude_ids=exclude_ids
                        ),
                    }
                )
                build_bucket_management(bucket.id, depth + 1)

        build_bucket_management(None, 0)

    return render(
        request,
        "tracker/time_settings.html",
        {
            "layouts": layouts,
            "layout": layout,
            "buckets": buckets,
            "bucket_options": bucket_options,
            "bucket_management": bucket_management,
        },
    )


@require_POST
@login_required
def time_level_select(request):
    layout_id = request.POST.get("layout_id")
    window_key = request.POST.get("time_window")
    bucket_id = request.POST.get("bucket_id")
    if not layout_id:
        return HttpResponseBadRequest("Missing layout")
    try:
        layout_id_int = int(layout_id)
    except ValueError:
        return HttpResponseBadRequest("Invalid layout")
    current_bucket_id = int(bucket_id) if bucket_id else None

    try:
        payload = select_from_level_for_user(
            user=request.user,
            layout_id=layout_id_int,
            bucket_id=current_bucket_id,
            time_window_key=window_key,
        )
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))

    if payload is None:
        payload = {
            "id": 0,
            "title": "Nothing to select at this level.",
        }

    response = JsonResponse(payload)
    response["HX-Trigger"] = json.dumps({"action-toast": payload})
    return response


@require_POST
@login_required
def time_layout_create(request):
    next_url = request.POST.get("next")
    name = (request.POST.get("layout_name") or "").strip()
    description = (request.POST.get("layout_description") or "").strip()
    if not name:
        messages.error(request, "Layout name is required.")
        return redirect("time_dashboard")

    try:
        layout = TimeLayout.objects.create(
            user=request.user, name=name, description=description
        )
    except IntegrityError:
        messages.error(request, "Layout name already exists.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("time_dashboard")

    messages.success(request, "Layout created.")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(f"{reverse('time_settings')}?layout={layout.id}")
    return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")


@require_POST
@login_required
def time_layout_update(request):
    next_url = request.POST.get("next")
    layout_id = request.POST.get("layout_id")
    name = (request.POST.get("layout_name") or "").strip()
    description = (request.POST.get("layout_description") or "").strip()
    if not layout_id:
        messages.error(request, "Layout not found.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("time_dashboard")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    if not name:
        messages.error(request, "Layout name is required.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    layout.name = name
    layout.description = description
    try:
        layout.save(update_fields=["name", "description"])
    except IntegrityError:
        messages.error(request, "Layout name already exists.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    messages.success(request, "Layout updated.")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")


@require_POST
@login_required
def time_layout_delete(request):
    next_url = request.POST.get("next")
    layout_id = request.POST.get("layout_id")
    if not layout_id:
        messages.error(request, "Layout not found.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("time_dashboard")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    layout.delete()
    messages.success(request, "Layout deleted.")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("time_dashboard")


@require_POST
@login_required
def time_bucket_create(request):
    next_url = request.POST.get("next")
    layout_id = request.POST.get("layout_id")
    name = (request.POST.get("bucket_name") or "").strip()
    parent_id = request.POST.get("parent_id") or None
    if not layout_id:
        messages.error(request, "Layout not found.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("time_dashboard")
    if not name:
        messages.error(request, "Bucket name is required.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("time_dashboard")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    parent = None
    if parent_id:
        parent = get_object_or_404(TimeBucket, id=parent_id, layout=layout)

    try:
        TimeBucket.objects.create(layout=layout, name=name, parent=parent)
    except IntegrityError:
        messages.error(request, "Bucket name already exists under that parent.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    messages.success(request, "Bucket created.")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")


@require_POST
@login_required
def time_bucket_update(request):
    next_url = request.POST.get("next")
    layout_id = request.POST.get("layout_id")
    bucket_id = request.POST.get("bucket_id")
    name = (request.POST.get("bucket_name") or "").strip()
    parent_id = request.POST.get("parent_id") or None
    if not layout_id or not bucket_id:
        messages.error(request, "Bucket not found.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("time_dashboard")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    bucket = get_object_or_404(TimeBucket, id=bucket_id, layout=layout)
    if not name:
        messages.error(request, "Bucket name is required.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    parent = None
    if parent_id:
        parent = get_object_or_404(TimeBucket, id=parent_id, layout=layout)

    if parent is not None and parent.id == bucket.id:
        messages.error(request, "Bucket cannot be its own parent.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    buckets = list(TimeBucket.objects.filter(layout=layout).select_related("parent"))
    descendants = build_bucket_descendants(buckets)
    if parent is not None and parent.id in descendants.get(bucket.id, set()):
        messages.error(request, "Bucket cannot be moved under its descendant.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    bucket.name = name
    bucket.parent = parent
    try:
        bucket.save(update_fields=["name", "parent"])
    except IntegrityError:
        messages.error(request, "Bucket name already exists under that parent.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    messages.success(request, "Bucket updated.")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")


@require_POST
@login_required
def time_bucket_delete(request):
    next_url = request.POST.get("next")
    layout_id = request.POST.get("layout_id")
    bucket_id = request.POST.get("bucket_id")
    delete_mode = request.POST.get("delete_mode") or "promote"
    if not layout_id or not bucket_id:
        messages.error(request, "Bucket not found.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("time_dashboard")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    bucket = get_object_or_404(TimeBucket, id=bucket_id, layout=layout)

    if delete_mode not in {"promote", "cascade"}:
        messages.error(request, "Delete mode is invalid.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    if delete_mode == "cascade":
        bucket.delete()
        messages.success(request, "Bucket and its children deleted.")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    with transaction.atomic():
        TimeBucket.objects.filter(layout=layout, parent=bucket).update(
            parent=bucket.parent
        )
        bucket.delete()

    messages.success(request, "Bucket deleted and children promoted.")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")


@require_POST
@login_required
def time_assignment_update(request):
    layout_id = request.POST.get("layout_id")
    item_id = request.POST.get("item_id")
    action = request.POST.get("action")
    next_url = request.POST.get("next")
    if not layout_id or not item_id or not action:
        return redirect("time_dashboard")

    layout = get_object_or_404(TimeLayout, id=layout_id, user=request.user)
    user_item = get_object_or_404(UserItem, id=item_id, user=request.user)

    def response_redirect():
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect(f"{reverse('time_dashboard')}?layout={layout.id}")

    if action == "ignore":
        ignore_item(layout, user_item)
        return response_redirect()

    if action == "unignore":
        unignore_item(layout, user_item)
        return response_redirect()

    if action == "unassign":
        unassign_item(layout, user_item)
        return response_redirect()

    if action == "assign":
        bucket_id = request.POST.get("bucket_id")
        if not bucket_id:
            return response_redirect()
        bucket = get_object_or_404(TimeBucket, id=bucket_id, layout=layout)
        assign_item(layout, user_item, bucket)
        return response_redirect()

    return response_redirect()
