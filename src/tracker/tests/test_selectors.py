from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from tracker.actions.selectors import RandomWeightedTimeSelector
from tracker.models import UserItem, UserItemHistory
from tracker.services.selection import apply_selector_eligibility


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
class SelectorEligibilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="selector",
            password="password",
        )
        self.item_fresh = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Fresh",
        )
        self.item_done = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Done",
        )
        self.item_redo = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Redo",
            is_redoing=True,
        )

        UserItemHistory.objects.create(
            user_item=self.item_done,
            event_type=UserItemHistory.Event.COMPLETED,
        )
        UserItemHistory.objects.create(
            user_item=self.item_redo,
            event_type=UserItemHistory.Event.COMPLETED,
        )

    def test_apply_selector_eligibility(self):
        qs = apply_selector_eligibility(UserItem.objects.filter(user=self.user))
        ids = {item.id for item in qs}
        self.assertIn(self.item_fresh.id, ids)
        self.assertIn(self.item_redo.id, ids)
        self.assertNotIn(self.item_done.id, ids)

    @patch("tracker.actions.selectors.random.choices")
    def test_random_weighted_time_uses_time_window(self, mock_choices):
        fresh_start = timezone.now() - timedelta(minutes=30)
        fresh_end = fresh_start + timedelta(minutes=5)
        UserItemHistory.objects.create(
            user_item=self.item_fresh,
            event_type=UserItemHistory.Event.REVISITED,
            started_at=fresh_start,
            ended_at=fresh_end,
        )
        old_start = timezone.now() - timedelta(days=400)
        old_end = old_start + timedelta(minutes=5)
        UserItemHistory.objects.create(
            user_item=self.item_redo,
            event_type=UserItemHistory.Event.REVISITED,
            started_at=old_start,
            ended_at=old_end,
        )

        qs = UserItem.objects.filter(user=self.user).order_by("id")
        selector = RandomWeightedTimeSelector()
        mock_choices.return_value = [self.item_fresh]

        selector(qs, user=self.user, time_window="last_7")
        weights = mock_choices.call_args.kwargs["weights"]

        self.assertGreater(weights[1], 0)
        self.assertGreater(weights[0], 0)
        self.assertNotEqual(weights[0], weights[1])
