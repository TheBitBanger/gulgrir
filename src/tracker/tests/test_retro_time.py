from datetime import datetime, timedelta
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tracker.models import UserItem, UserItemHistory
from tracker.views.useritems import parse_retro_duration, parse_retro_time


class RetroDurationParserTests(TestCase):
    def test_accepts_hours_minutes_seconds(self):
        duration, error = parse_retro_duration("1h 20m 10s")
        self.assertIsNone(error)
        self.assertEqual(duration, timedelta(hours=1, minutes=20, seconds=10))

    def test_accepts_compact_format(self):
        duration, error = parse_retro_duration("2h15m")
        self.assertIsNone(error)
        self.assertEqual(duration, timedelta(hours=2, minutes=15))

    def test_rejects_plain_numbers(self):
        duration, error = parse_retro_duration("10")
        self.assertIsNone(duration)
        self.assertEqual(error, "Use h/m/s (e.g. 1h 20m 10s)")

    def test_rejects_invalid_units(self):
        duration, error = parse_retro_duration("1d")
        self.assertIsNone(duration)
        self.assertEqual(error, "Use h/m/s (e.g. 1h 20m 10s)")

    def test_rejects_over_24_hours(self):
        duration, error = parse_retro_duration("24h 1s")
        self.assertIsNone(duration)
        self.assertEqual(error, "Duration must be 24h or less")

    def test_accepts_time_without_leading_zero(self):
        parsed, error = parse_retro_time("9:00")
        self.assertIsNone(error)
        self.assertEqual(parsed.hour, 9)
        self.assertEqual(parsed.minute, 0)


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
class RetroTimeEntryTests(TestCase):
    def setUp(self):
        self.user = cast(Any, get_user_model().objects).create_user(
            username="tester",
        )
        self.user.profile.timezone = "UTC"
        self.user.profile.save(update_fields=["timezone"])
        self.user_item = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Retro Project",
        )

    def test_retro_time_entry_creates_history(self):
        self.client.force_login(self.user)
        url = reverse("useritem_timer_add", kwargs={"pk": self.user_item.pk})
        payload = {
            "retro_date": "2026-03-08",
            "retro_start_time": "",
            "retro_duration": "1h 30m 10s",
        }

        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)

        history = UserItemHistory.objects.get(user_item=self.user_item)
        tz = timezone.get_current_timezone()
        expected_start = timezone.make_aware(datetime(2026, 3, 8, 0, 0, 0), tz)
        expected_end = expected_start + timedelta(hours=1, minutes=30, seconds=10)
        self.assertEqual(history.event_type, UserItemHistory.Event.REVISITED)
        self.assertEqual(history.started_at, expected_start)
        self.assertEqual(history.ended_at, expected_end)

    def test_retro_time_entry_invalid_duration(self):
        self.client.force_login(self.user)
        url = reverse("useritem_timer_add", kwargs={"pk": self.user_item.pk})
        payload = {
            "retro_date": "2026-03-08",
            "retro_start_time": "00:00",
            "retro_duration": "10",
        }

        response = self.client.post(url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Duration: Use h/m/s (e.g. 1h 20m 10s)", messages)

    def test_retro_time_entry_accepts_start_time_without_leading_zero(self):
        self.client.force_login(self.user)
        url = reverse("useritem_timer_add", kwargs={"pk": self.user_item.pk})
        payload = {
            "retro_date": "2026-03-08",
            "retro_start_time": "9:00",
            "retro_duration": "30m",
        }

        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)

        history = UserItemHistory.objects.get(user_item=self.user_item)
        tz = timezone.get_current_timezone()
        expected_start = timezone.make_aware(datetime(2026, 3, 8, 9, 0, 0), tz)
        self.assertEqual(history.started_at, expected_start)
