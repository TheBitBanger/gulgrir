from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker.models import UserItem


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
class UserItemCreateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="creator",
            password="password",
        )

    def test_created_by_set_on_create(self):
        self.client.force_login(self.user)
        url = reverse("useritem_add")
        payload = {
            "is_project": "on",
            "title_override": "Created by me",
            "shelf": UserItem.Shelf.BACKLOG,
            "tier": UserItem.Tier.UNRATED,
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        item = UserItem.objects.get(user=self.user, title_override="Created by me")
        self.assertEqual(item.created_by, self.user)
