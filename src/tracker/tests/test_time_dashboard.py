from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
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

    def test_unassign_clears_bucket(self):
        self.client.force_login(self.user)
        url = reverse("time_assignment_update")
        payload = {
            "layout_id": self.layout.id,
            "item_id": self.item_work.id,
            "action": "unassign",
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        assignment = TimeBucketAssignment.objects.get(
            layout=self.layout,
            user_item=self.item_work,
        )
        self.assertFalse(assignment.is_ignored)
        self.assertIsNone(assignment.bucket)

    def test_time_settings_shows_assigned_items(self):
        self.client.force_login(self.user)
        url = f"{reverse('time_settings')}?layout={self.layout.id}"
        response = self.client.get(url)
        self.assertContains(response, "Work item")

    def test_update_layout(self):
        self.client.force_login(self.user)
        url = reverse("time_layout_update")
        payload = {
            "layout_id": self.layout.id,
            "layout_name": "Balance updated",
            "layout_description": "New desc",
        }
        response = self.client.post(url, payload, follow=True)
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.name, "Balance updated")
        self.assertEqual(self.layout.description, "New desc")
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Layout updated.", messages)

    def test_delete_layout(self):
        self.client.force_login(self.user)
        url = reverse("time_layout_delete")
        response = self.client.post(url, {"layout_id": self.layout.id}, follow=True)
        self.assertFalse(TimeLayout.objects.filter(id=self.layout.id).exists())
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Layout deleted.", messages)

    def test_update_bucket(self):
        self.client.force_login(self.user)
        url = reverse("time_bucket_update")
        payload = {
            "layout_id": self.layout.id,
            "bucket_id": self.bucket_work.id,
            "bucket_name": "Work updated",
            "parent_id": "",
        }
        response = self.client.post(url, payload, follow=True)
        self.bucket_work.refresh_from_db()
        self.assertEqual(self.bucket_work.name, "Work updated")
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Bucket updated.", messages)

    def test_reparent_bucket(self):
        self.client.force_login(self.user)
        url = reverse("time_bucket_update")
        payload = {
            "layout_id": self.layout.id,
            "bucket_id": self.bucket_play.id,
            "bucket_name": self.bucket_play.name,
            "parent_id": self.bucket_work.id,
        }
        response = self.client.post(url, payload, follow=True)
        self.bucket_play.refresh_from_db()
        self.assertEqual(self.bucket_play.parent, self.bucket_work)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Bucket updated.", messages)

    def test_reparent_bucket_cycle_error(self):
        child = TimeBucket.objects.create(
            layout=self.layout,
            name="Child",
            parent=self.bucket_work,
        )
        self.client.force_login(self.user)
        url = reverse("time_bucket_update")
        payload = {
            "layout_id": self.layout.id,
            "bucket_id": self.bucket_work.id,
            "bucket_name": self.bucket_work.name,
            "parent_id": child.id,
        }
        response = self.client.post(url, payload, follow=True)
        self.bucket_work.refresh_from_db()
        self.assertIsNone(self.bucket_work.parent)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Bucket cannot be moved under its descendant.", messages)

    def test_delete_bucket_promote_children(self):
        child = TimeBucket.objects.create(
            layout=self.layout,
            name="Child",
            parent=self.bucket_work,
        )
        self.client.force_login(self.user)
        url = reverse("time_bucket_delete")
        payload = {
            "layout_id": self.layout.id,
            "bucket_id": self.bucket_work.id,
            "delete_mode": "promote",
        }
        response = self.client.post(url, payload, follow=True)
        self.assertFalse(TimeBucket.objects.filter(id=self.bucket_work.id).exists())
        child.refresh_from_db()
        self.assertIsNone(child.parent)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Bucket deleted and children promoted.", messages)

    def test_delete_bucket_cascade(self):
        child = TimeBucket.objects.create(
            layout=self.layout,
            name="Child",
            parent=self.bucket_work,
        )
        self.client.force_login(self.user)
        url = reverse("time_bucket_delete")
        payload = {
            "layout_id": self.layout.id,
            "bucket_id": self.bucket_work.id,
            "delete_mode": "cascade",
        }
        response = self.client.post(url, payload, follow=True)
        self.assertFalse(TimeBucket.objects.filter(id=self.bucket_work.id).exists())
        self.assertFalse(TimeBucket.objects.filter(id=child.id).exists())
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Bucket and its children deleted.", messages)
