from datetime import time, timedelta
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tracker.models import (
    FocusSprint,
    Profile,
    TimeBucket,
    TimeBucketAssignment,
    TimeLayout,
    UserItem,
    UserItemHistory,
)
from tracker.services.focus_sprint import (
    build_ghost_suggestion,
    build_open_sprint_snapshots,
)


class FocusSprintServiceTests(TestCase):
    def setUp(self):
        self.user = cast(Any, get_user_model().objects).create_user(
            username="focus-user"
        )
        self.layout = TimeLayout.objects.create(user=self.user, name="Main")
        self.bucket = TimeBucket.objects.create(layout=self.layout, name="Project")
        self.item = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Workstream",
        )
        TimeBucketAssignment.objects.create(
            layout=self.layout,
            user_item=self.item,
            bucket=self.bucket,
            assignment_mode=TimeBucketAssignment.Mode.BUCKET,
        )

    def test_item_scope_progress_and_stage(self):
        sprint = FocusSprint.objects.create(
            user=self.user,
            scope_type=FocusSprint.ScopeType.ITEM,
            user_item=self.item,
            target_minutes=120,
            overflow_soft_cap_minutes=60,
        )
        end = timezone.now()
        UserItemHistory.objects.create(
            user_item=self.item,
            event_type=UserItemHistory.Event.REVISITED,
            happened_at=end,
            started_at=end - timedelta(minutes=70),
            ended_at=end,
        )

        snapshots = build_open_sprint_snapshots(user=self.user)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].sprint_id, sprint.id)
        self.assertEqual(snapshots[0].tracked_minutes, 70)
        self.assertEqual(snapshots[0].stage, "nourished")

    def test_bucket_scope_uses_current_assignments(self):
        sprint = FocusSprint.objects.create(
            user=self.user,
            scope_type=FocusSprint.ScopeType.BUCKET,
            time_bucket=self.bucket,
            target_minutes=60,
            overflow_soft_cap_minutes=30,
        )
        end = timezone.now()
        UserItemHistory.objects.create(
            user_item=self.item,
            event_type=UserItemHistory.Event.REVISITED,
            happened_at=end,
            started_at=end - timedelta(minutes=65),
            ended_at=end,
        )

        snapshots = build_open_sprint_snapshots(user=self.user)
        self.assertEqual(snapshots[0].sprint_id, sprint.id)
        self.assertEqual(snapshots[0].stage, "sated")

    def test_progress_counts_same_day_time_after_cutoff(self):
        sprint = FocusSprint.objects.create(
            user=self.user,
            scope_type=FocusSprint.ScopeType.BUCKET,
            time_bucket=self.bucket,
            target_minutes=600,
            overflow_soft_cap_minutes=300,
        )
        ended_at = timezone.now() - timedelta(hours=2)
        UserItemHistory.objects.create(
            user_item=self.item,
            event_type=UserItemHistory.Event.REVISITED,
            happened_at=ended_at,
            started_at=ended_at - timedelta(hours=2),
            ended_at=ended_at,
        )

        snapshots = build_open_sprint_snapshots(user=self.user)
        self.assertEqual(snapshots[0].sprint_id, sprint.id)
        self.assertGreaterEqual(snapshots[0].tracked_minutes, 120)

    def test_progress_excludes_time_before_goal_day_cutoff(self):
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.time_dashboard_day_cutoff = time(4, 0)
        profile.save(update_fields=["time_dashboard_day_cutoff"])

        sprint = FocusSprint.objects.create(
            user=self.user,
            scope_type=FocusSprint.ScopeType.BUCKET,
            time_bucket=self.bucket,
            target_minutes=600,
            overflow_soft_cap_minutes=300,
        )
        now = timezone.localtime()
        day_start = now.replace(hour=4, minute=0, second=0, microsecond=0)
        before_cutoff_end = day_start - timedelta(minutes=30)
        UserItemHistory.objects.create(
            user_item=self.item,
            event_type=UserItemHistory.Event.REVISITED,
            happened_at=before_cutoff_end,
            started_at=before_cutoff_end - timedelta(hours=1),
            ended_at=before_cutoff_end,
        )

        snapshots = build_open_sprint_snapshots(user=self.user)
        self.assertEqual(snapshots[0].sprint_id, sprint.id)
        self.assertEqual(snapshots[0].tracked_minutes, 0)

    def test_ghost_suggestion_appears_when_no_open_sprints(self):
        suggestion = build_ghost_suggestion(user=self.user, sprints=[])
        self.assertIsNotNone(suggestion)

    def test_ghost_suggestion_appears_even_when_goal_not_met(self):
        sprint = FocusSprint.objects.create(
            user=self.user,
            scope_type=FocusSprint.ScopeType.ITEM,
            user_item=self.item,
            target_minutes=600,
            overflow_soft_cap_minutes=300,
        )
        snapshots = build_open_sprint_snapshots(user=self.user)
        self.assertEqual(snapshots[0].sprint_id, sprint.id)
        self.assertEqual(snapshots[0].stage, "starved")

        suggestion = build_ghost_suggestion(user=self.user, sprints=snapshots)
        self.assertIsNotNone(suggestion)

    def test_progress_counts_overlap_when_entry_ends_in_future(self):
        sprint = FocusSprint.objects.create(
            user=self.user,
            scope_type=FocusSprint.ScopeType.ITEM,
            user_item=self.item,
            target_minutes=120,
            overflow_soft_cap_minutes=60,
        )
        now = timezone.now()
        UserItemHistory.objects.create(
            user_item=self.item,
            event_type=UserItemHistory.Event.REVISITED,
            happened_at=now + timedelta(hours=2),
            started_at=now - timedelta(hours=1),
            ended_at=now + timedelta(hours=2),
        )

        snapshots = build_open_sprint_snapshots(user=self.user)
        self.assertEqual(snapshots[0].sprint_id, sprint.id)
        self.assertGreaterEqual(snapshots[0].tracked_minutes, 60)


class FocusSprintViewTests(TestCase):
    def setUp(self):
        self.user = cast(Any, get_user_model().objects).create_user(
            username="focus-view",
            password="pw",
        )
        self.client.force_login(self.user)
        self.layout = TimeLayout.objects.create(user=self.user, name="Main")
        self.bucket = TimeBucket.objects.create(layout=self.layout, name="Work")
        self.item = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Focus Item",
        )

    def test_binding_creates_item_sprint(self):
        response = self.client.post(
            reverse("focus_bind"),
            {
                "scope_type": "item",
                "user_item_id": self.item.id,
                "target": "10h",
                "overflow_cap": "5h",
                "next": reverse("useritem_dashboard"),
            },
        )
        self.assertEqual(response.status_code, 302)
        sprint = FocusSprint.objects.get(user=self.user)
        self.assertEqual(sprint.scope_type, FocusSprint.ScopeType.ITEM)
        self.assertEqual(sprint.target_minutes, 600)
        self.assertEqual(sprint.overflow_soft_cap_minutes, 300)

    def test_releasing_closes_only_selected_sprint(self):
        sprint_a = FocusSprint.objects.create(
            user=self.user,
            scope_type=FocusSprint.ScopeType.ITEM,
            user_item=self.item,
            target_minutes=600,
            overflow_soft_cap_minutes=300,
        )
        other_item = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Other",
        )
        sprint_b = FocusSprint.objects.create(
            user=self.user,
            scope_type=FocusSprint.ScopeType.ITEM,
            user_item=other_item,
            target_minutes=600,
            overflow_soft_cap_minutes=300,
        )

        response = self.client.post(
            reverse("focus_release", kwargs={"sprint_id": sprint_a.id}),
            {"next": reverse("useritem_dashboard")},
        )
        self.assertEqual(response.status_code, 302)
        sprint_a.refresh_from_db()
        sprint_b.refresh_from_db()
        self.assertIsNotNone(sprint_a.closed_at)
        self.assertIsNone(sprint_b.closed_at)

    def test_profile_form_saves_focus_defaults(self):
        response = self.client.post(
            reverse("focus_settings"),
            {
                "focus_default_target_hours": "15",
                "focus_default_overflow_soft_cap_hours": "5h",
            },
        )
        self.assertEqual(response.status_code, 302)
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.focus_default_target_minutes, 900)
        self.assertEqual(profile.focus_default_overflow_soft_cap_minutes, 300)
