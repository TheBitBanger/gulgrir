from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker.models import TimeBucket, TimeBucketAssignment, TimeLayout, UserItem
from tracker.views import build_chart_entries


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
class TimeDashboardAssignmentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dashboard",
            password="password",
        )
        self.layout = TimeLayout.objects.create(user=self.user, name="Balance")
        self.bucket_work = TimeBucket.objects.create(
            layout=self.layout,
            name="Work",
        )
        self.bucket_play = TimeBucket.objects.create(
            layout=self.layout,
            name="Play",
        )
        self.item_work = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Work item",
        )
        self.item_unassigned = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Unassigned item",
        )
        self.item_ignored = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Ignored item",
        )

        TimeBucketAssignment.objects.create(
            layout=self.layout,
            user_item=self.item_work,
            bucket=self.bucket_work,
        )
        TimeBucketAssignment.objects.create(
            layout=self.layout,
            user_item=self.item_ignored,
            is_ignored=True,
        )

    def test_build_chart_entries_bucket_priority(self):
        durations = {
            self.item_work.id: int(timedelta(hours=1).total_seconds()),
            self.item_unassigned.id: int(timedelta(minutes=30).total_seconds()),
            self.item_ignored.id: int(timedelta(minutes=20).total_seconds()),
        }
        user_items = {
            self.item_work.id: self.item_work,
            self.item_unassigned.id: self.item_unassigned,
            self.item_ignored.id: self.item_ignored,
        }
        assignments = {
            a.user_item_id: a
            for a in TimeBucketAssignment.objects.filter(layout=self.layout)
        }
        buckets = list(TimeBucket.objects.filter(layout=self.layout))

        result = build_chart_entries(
            layout=self.layout,
            buckets=buckets,
            assignments=assignments,
            item_durations=durations,
            user_items=user_items,
            bucket_id=None,
            top_n=10,
        )

        labels = [entry["label"] for entry in result["entries"]]
        self.assertIn("Work", labels)
        self.assertIn("Play", labels)
        self.assertIn("Unassigned item", labels)
        self.assertEqual(len(result["ignored_items"]), 1)
        self.assertEqual(len(result["unassigned_items"]), 1)

    def test_ignore_assignment_clears_bucket(self):
        self.client.force_login(self.user)
        url = reverse("time_assignment_update")
        payload = {
            "layout_id": self.layout.id,
            "item_id": self.item_work.id,
            "action": "ignore",
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        assignment = TimeBucketAssignment.objects.get(
            layout=self.layout,
            user_item=self.item_work,
        )
        self.assertTrue(assignment.is_ignored)
        self.assertIsNone(assignment.bucket)

    def test_assign_unignores(self):
        self.client.force_login(self.user)
        url = reverse("time_assignment_update")
        payload = {
            "layout_id": self.layout.id,
            "item_id": self.item_ignored.id,
            "action": "assign",
            "bucket_id": self.bucket_play.id,
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        assignment = TimeBucketAssignment.objects.get(
            layout=self.layout,
            user_item=self.item_ignored,
        )
        self.assertFalse(assignment.is_ignored)
        self.assertEqual(assignment.bucket, self.bucket_play)
