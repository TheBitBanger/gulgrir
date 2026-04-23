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
class UserItemRestartTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="restart",
        )
        self.item = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Restartable",
        )

    def test_restart_requires_completion(self):
        self.client.force_login(self.user)
        url = reverse("useritem_restart", kwargs={"pk": self.item.pk})
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_redoing)

    def test_restart_sets_redoing(self):
        UserItemHistory.objects.create(
            user_item=self.item,
            event_type=UserItemHistory.Event.COMPLETED,
        )
        self.item.shelf = UserItem.Shelf.DONE
        self.item.save(update_fields=["shelf"])
        self.client.force_login(self.user)
        url = reverse("useritem_restart", kwargs={"pk": self.item.pk})
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_redoing)
        self.assertEqual(self.item.shelf, UserItem.Shelf.IN_PROGRESS)

    def test_completed_at_clears_redoing(self):
        self.item.is_redoing = True
        self.item.save(update_fields=["is_redoing"])
        self.client.force_login(self.user)
        url = reverse("useritem_detail", kwargs={"pk": self.item.pk})
        payload = {
            "item": "",
            "is_project": "on",
            "title_override": self.item.title_override,
            "shelf": self.item.shelf,
            "tier": self.item.tier,
            "completed_at": timezone.now().isoformat(),
        }
        response = self.client.post(url, payload, follow=True)
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_redoing)

    def test_complete_endpoint_creates_history(self):
        self.client.force_login(self.user)
        url = reverse("useritem_complete", kwargs={"pk": self.item.pk})
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            UserItemHistory.objects.filter(
                user_item=self.item,
                event_type=UserItemHistory.Event.COMPLETED,
            ).exists()
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.shelf, UserItem.Shelf.DONE)
