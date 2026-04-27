from datetime import datetime, timedelta
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tracker.models import UserItem, UserItemHistory


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
class TimeEntryEditTests(TestCase):
    def setUp(self):
        self.user = cast(Any, get_user_model().objects).create_user(
            username="entry-editor",
        )
        self.user.profile.timezone = "UTC"
        self.user.profile.save(update_fields=["timezone"])

        self.other_user = cast(Any, get_user_model().objects).create_user(
            username="other-user",
        )

        self.user_item = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Editable item",
        )
        self.target_item = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Target item",
        )
        self.other_user_item = UserItem.objects.create(
            user=self.other_user,
            is_project=True,
            title_override="Other user item",
        )

        tz = timezone.get_current_timezone()
        self.original_start = timezone.make_aware(datetime(2026, 4, 1, 9, 0), tz)
        self.original_end = self.original_start + timedelta(minutes=45)

        self.entry = UserItemHistory.objects.create(
            user_item=self.user_item,
            event_type=UserItemHistory.Event.REVISITED,
            happened_at=self.original_end,
            started_at=self.original_start,
            ended_at=self.original_end,
        )
        self.completed_entry = UserItemHistory.objects.create(
            user_item=self.user_item,
            event_type=UserItemHistory.Event.COMPLETED,
            happened_at=self.original_end,
        )

    def test_updates_revisited_entry_with_start_and_end(self):
        self.client.force_login(self.user)
        url = reverse(
            "useritem_history_update",
            kwargs={"pk": self.user_item.pk, "history_pk": self.entry.pk},
        )
        response = self.client.post(
            url,
            {
                "started_at": "2026-04-01T10:00",
                "edit_mode": "end",
                "ended_at": "2026-04-01T11:30",
                "target_user_item": str(self.user_item.pk),
            },
        )
        self.assertEqual(response.status_code, 302)

        self.entry.refresh_from_db()
        started_at = self.entry.started_at
        ended_at = self.entry.ended_at
        self.assertIsNotNone(started_at)
        self.assertIsNotNone(ended_at)
        if started_at is None or ended_at is None:
            self.fail("Expected started_at and ended_at to be set")
        self.assertEqual(started_at.hour, 10)
        self.assertEqual(started_at.minute, 0)
        self.assertEqual(ended_at.hour, 11)
        self.assertEqual(ended_at.minute, 30)
        self.assertEqual(self.entry.duration, timedelta(hours=1, minutes=30))
        self.assertEqual(self.entry.happened_at, self.entry.ended_at)

    def test_updates_revisited_entry_with_duration(self):
        self.client.force_login(self.user)
        url = reverse(
            "useritem_history_update",
            kwargs={"pk": self.user_item.pk, "history_pk": self.entry.pk},
        )
        response = self.client.post(
            url,
            {
                "started_at": "2026-04-01T08:15",
                "edit_mode": "duration",
                "duration": "1h 20m",
                "target_user_item": str(self.user_item.pk),
            },
        )
        self.assertEqual(response.status_code, 302)

        self.entry.refresh_from_db()
        started_at = self.entry.started_at
        self.assertIsNotNone(started_at)
        if started_at is None:
            self.fail("Expected started_at to be set")
        self.assertEqual(started_at.hour, 8)
        self.assertEqual(started_at.minute, 15)
        self.assertEqual(self.entry.duration, timedelta(hours=1, minutes=20))
        self.assertEqual(self.entry.happened_at, self.entry.ended_at)

    def test_can_reassign_entry_to_another_owned_item(self):
        self.client.force_login(self.user)
        url = reverse(
            "useritem_history_update",
            kwargs={"pk": self.user_item.pk, "history_pk": self.entry.pk},
        )
        response = self.client.post(
            url,
            {
                "started_at": "2026-04-01T08:15",
                "edit_mode": "duration",
                "duration": "30m",
                "target_user_item": str(self.target_item.pk),
            },
        )
        self.assertEqual(response.status_code, 302)

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.user_item_id, self.target_item.pk)

    def test_completed_entries_cannot_be_edited(self):
        self.client.force_login(self.user)
        url = reverse(
            "useritem_history_update",
            kwargs={
                "pk": self.user_item.pk,
                "history_pk": self.completed_entry.pk,
            },
        )
        response = self.client.post(
            url,
            {
                "started_at": "2026-04-01T08:15",
                "edit_mode": "duration",
                "duration": "30m",
                "target_user_item": str(self.target_item.pk),
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_cannot_reassign_entry_to_other_users_item(self):
        self.client.force_login(self.user)
        url = reverse(
            "useritem_history_update",
            kwargs={"pk": self.user_item.pk, "history_pk": self.entry.pk},
        )
        response = self.client.post(
            url,
            {
                "started_at": "2026-04-01T08:15",
                "edit_mode": "duration",
                "duration": "30m",
                "target_user_item": str(self.other_user_item.pk),
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_invalid_end_before_start_shows_error(self):
        self.client.force_login(self.user)
        url = reverse(
            "useritem_history_update",
            kwargs={"pk": self.user_item.pk, "history_pk": self.entry.pk},
        )
        response = self.client.post(
            url,
            {
                "started_at": "2026-04-01T11:00",
                "edit_mode": "end",
                "ended_at": "2026-04-01T10:00",
                "target_user_item": str(self.user_item.pk),
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("End: Must be after start", messages)
