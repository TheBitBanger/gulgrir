from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import FocusSprint, Profile, TimeBucket, UserItem
from ..services.focus_sprint import parse_goal_input_minutes, profile_defaults


@require_POST
@login_required
def focus_bind(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    defaults = profile_defaults(profile)

    scope_type = (request.POST.get("scope_type") or "").strip()
    target_raw = (request.POST.get("target") or "").strip()
    cap_raw = (request.POST.get("overflow_cap") or "").strip()

    target_minutes = parse_goal_input_minutes(target_raw) if target_raw else None
    cap_minutes = parse_goal_input_minutes(cap_raw) if cap_raw else None

    target = (
        target_minutes if target_minutes is not None else defaults["target_minutes"]
    )
    cap = (
        cap_minutes
        if cap_minutes is not None
        else defaults["overflow_soft_cap_minutes"]
    )

    if target <= 0:
        messages.error(request, "Bind failed: target must be positive.")
        return redirect(request.POST.get("next") or "useritem_dashboard")
    if cap < 0:
        messages.error(request, "Bind failed: overflow soft cap must be zero or more.")
        return redirect(request.POST.get("next") or "useritem_dashboard")

    if scope_type == FocusSprint.ScopeType.ITEM:
        item_id = request.POST.get("user_item_id")
        user_item = get_object_or_404(UserItem, pk=item_id, user=request.user)
        FocusSprint.objects.create(
            user=request.user,
            scope_type=FocusSprint.ScopeType.ITEM,
            user_item=user_item,
            target_minutes=target,
            overflow_soft_cap_minutes=cap,
        )
    elif scope_type == FocusSprint.ScopeType.BUCKET:
        bucket_id = request.POST.get("time_bucket_id")
        bucket = get_object_or_404(TimeBucket, pk=bucket_id, layout__user=request.user)
        FocusSprint.objects.create(
            user=request.user,
            scope_type=FocusSprint.ScopeType.BUCKET,
            time_bucket=bucket,
            target_minutes=target,
            overflow_soft_cap_minutes=cap,
        )
    else:
        messages.error(request, "Bind failed: choose an item or bucket.")
        return redirect(request.POST.get("next") or "useritem_dashboard")

    messages.success(request, "Goal bound.")
    return redirect(request.POST.get("next") or "useritem_dashboard")


@require_POST
@login_required
def focus_release(request, sprint_id: int):
    sprint = get_object_or_404(FocusSprint, pk=sprint_id, user=request.user)
    if sprint.closed_at is None:
        sprint.closed_at = timezone.now()
        sprint.save(update_fields=["closed_at"])
        messages.success(request, "Goal released.")
    return redirect(request.POST.get("next") or "useritem_dashboard")


@require_POST
@login_required
def focus_bear_witness(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    defaults = profile_defaults(profile)
    kind = (request.POST.get("kind") or "").strip()
    next_url = request.POST.get("next") or "useritem_dashboard"

    if kind == "item":
        item_id = request.POST.get("id")
        user_item = get_object_or_404(UserItem, pk=item_id, user=request.user)
        FocusSprint.objects.create(
            user=request.user,
            scope_type=FocusSprint.ScopeType.ITEM,
            user_item=user_item,
            target_minutes=defaults["target_minutes"],
            overflow_soft_cap_minutes=defaults["overflow_soft_cap_minutes"],
        )
    elif kind == "bucket":
        bucket_id = request.POST.get("id")
        bucket = get_object_or_404(TimeBucket, pk=bucket_id, layout__user=request.user)
        FocusSprint.objects.create(
            user=request.user,
            scope_type=FocusSprint.ScopeType.BUCKET,
            time_bucket=bucket,
            target_minutes=defaults["target_minutes"],
            overflow_soft_cap_minutes=defaults["overflow_soft_cap_minutes"],
        )
    else:
        messages.error(request, "Suggestion could not be accepted.")
        return redirect(next_url)

    messages.success(request, "Suggestion accepted.")
    return redirect(next_url)
