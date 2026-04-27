from typing import Any, cast

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker.models import Item, UserItem


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
class UserItemCreateTests(TestCase):
    def setUp(self):
        self.user = cast(Any, get_user_model().objects).create_user(
            username="creator",
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

    def test_create_non_project_creates_global_item(self):
        self.client.force_login(self.user)
        url = reverse("useritem_add")
        payload = {
            "item_title": "Dune",
            "media_type": Item.MediaType.BOOK,
            "shelf": UserItem.Shelf.BACKLOG,
            "tier": UserItem.Tier.UNRATED,
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)

        global_item = Item.objects.get(title="Dune", media_type=Item.MediaType.BOOK)
        user_item = UserItem.objects.get(user=self.user, item=global_item)
        self.assertEqual(user_item.item_id, global_item.id)

    def test_create_non_project_reuses_existing_global_item(self):
        existing = Item.objects.create(title="Dune", media_type=Item.MediaType.BOOK)

        self.client.force_login(self.user)
        url = reverse("useritem_add")
        payload = {
            "item_title": "dune",
            "media_type": Item.MediaType.BOOK,
            "shelf": UserItem.Shelf.BACKLOG,
            "tier": UserItem.Tier.UNRATED,
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)

        self.assertEqual(Item.objects.filter(media_type=Item.MediaType.BOOK).count(), 1)
        user_item = UserItem.objects.get(user=self.user)
        self.assertEqual(user_item.item_id, existing.id)
