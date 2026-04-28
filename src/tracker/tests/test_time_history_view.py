from datetime import date, datetime, timedelta
from typing import Any, cast

from django.contrib.auth import get_user_model
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
class TimeHistoryViewTests(TestCase):
    def setUp(self):
        self.user = cast(Any, get_user_model().objects).create_user(
            username="history-viewer",
        )
        self.user_item = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="History project",
        )

    def _add_revisited_entry(self, start_at: datetime, minutes: int = 30) -> None:
        end_at = start_at + timedelta(minutes=minutes)
        UserItemHistory.objects.create(
            user_item=self.user_item,
            event_type=UserItemHistory.Event.REVISITED,
            happened_at=end_at,
            started_at=start_at,
            ended_at=end_at,
        )

    def test_useritem_detail_groups_entries_by_day(self):
        tz = timezone.get_current_timezone()
        same_day_a = timezone.make_aware(datetime(2026, 4, 20, 8, 0), tz)
        same_day_b = timezone.make_aware(datetime(2026, 4, 20, 10, 0), tz)
        other_day = timezone.make_aware(datetime(2026, 4, 19, 9, 0), tz)
        self._add_revisited_entry(same_day_a)
        self._add_revisited_entry(same_day_b)
        self._add_revisited_entry(other_day)

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("useritem_detail", kwargs={"pk": self.user_item.pk})
        )
        self.assertEqual(response.status_code, 200)

        groups = cast(list[dict[str, object]], response.context["history_day_groups"])
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(cast(list[object], groups[0]["entries"])), 2)
        trend = cast(list[dict[str, object]], response.context["history_trend"])
        self.assertEqual(len(trend), 30)
        self.assertEqual(sum(1 for row in trend if cast(bool, row["is_tick"])), 5)

    def test_useritem_detail_limits_to_30_days_and_exposes_load_older(self):
        tz = timezone.get_current_timezone()
        base = timezone.make_aware(datetime(2026, 4, 30, 9, 0), tz)
        for offset in range(35):
            self._add_revisited_entry(base - timedelta(days=offset), minutes=20)

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("useritem_detail", kwargs={"pk": self.user_item.pk})
        )
        self.assertEqual(response.status_code, 200)

        groups = cast(list[dict[str, object]], response.context["history_day_groups"])
        self.assertEqual(len(groups), 30)
        self.assertTrue(cast(bool, response.context["history_has_more"]))
        load_url = cast(str | None, response.context["history_load_older_url"])
        self.assertIsNotNone(load_url)
        self.assertIn("history_before=", load_url or "")
        trend = cast(list[dict[str, object]], response.context["history_trend"])
        self.assertEqual(len(trend), 30)
        self.assertTrue(any(cast(int, row["seconds"]) > 0 for row in trend))
        self.assertIn("bar_opacity", trend[0])

    def test_full_history_page_renders(self):
        tz = timezone.get_current_timezone()
        self._add_revisited_entry(timezone.make_aware(datetime(2026, 4, 21, 14, 0), tz))

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("useritem_time_history", kwargs={"pk": self.user_item.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("history_day_groups", response.context)
        self.assertIn("history_trend", response.context)

    def test_summary_uses_average_per_active_day(self):
        tz = timezone.get_current_timezone()
        self._add_revisited_entry(
            timezone.make_aware(datetime(2026, 4, 21, 10, 0), tz),
            minutes=30,
        )
        self._add_revisited_entry(
            timezone.make_aware(datetime(2026, 4, 21, 12, 0), tz),
            minutes=30,
        )
        self._add_revisited_entry(
            timezone.make_aware(datetime(2026, 4, 20, 9, 0), tz),
            minutes=30,
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("useritem_detail", kwargs={"pk": self.user_item.pk})
        )
        self.assertEqual(response.status_code, 200)

        summary = cast(dict[str, object], response.context["time_summary"])
        self.assertEqual(summary["active_day_count"], 2)
        self.assertEqual(summary["avg_per_day_display"], "00:45:00")

    def test_trend_tick_label_uses_user_date_preference(self):
        self.user.profile.date_format = "%d/%m/%Y"
        self.user.profile.save(update_fields=["date_format"])

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("useritem_detail", kwargs={"pk": self.user_item.pk})
        )
        self.assertEqual(response.status_code, 200)

        trend = cast(list[dict[str, object]], response.context["history_trend"])
        tick_row = next(row for row in trend if cast(bool, row["is_tick"]))
        tick_day = cast(date, tick_row["day"])
        self.assertEqual(tick_row["tick_label"], tick_day.strftime("%d/%m"))
