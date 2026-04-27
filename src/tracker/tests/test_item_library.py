from typing import Any, cast

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import IntegrityError
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
class ItemLibraryTests(TestCase):
    def setUp(self):
        self.user = cast(Any, get_user_model().objects).create_user(username="lib")

    def test_item_title_media_type_unique_case_insensitive(self):
        Item.objects.create(title="Dune", media_type=Item.MediaType.BOOK)
        with self.assertRaises(IntegrityError):
            Item.objects.create(title="dune", media_type=Item.MediaType.BOOK)

    def test_delete_unused_global_item(self):
        item = Item.objects.create(title="Unused", media_type=Item.MediaType.OTHER)
        self.client.force_login(self.user)

        response = self.client.post(reverse("item_delete", kwargs={"pk": item.pk}))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Item.objects.filter(pk=item.pk).exists())

    def test_cannot_delete_in_use_global_item(self):
        item = Item.objects.create(title="Used", media_type=Item.MediaType.OTHER)
        UserItem.objects.create(user=self.user, item=item)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("item_delete", kwargs={"pk": item.pk}),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Item.objects.filter(pk=item.pk).exists())
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("This global item is in use and cannot be deleted.", messages)

    def test_item_list_shows_usage_and_unused_indicator(self):
        used = Item.objects.create(title="Used", media_type=Item.MediaType.BOOK)
        Item.objects.create(title="Unused", media_type=Item.MediaType.BOOK)
        UserItem.objects.create(user=self.user, item=used)
        self.client.force_login(self.user)

        response = self.client.get(reverse("item_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unused")
        by_title = {
            row.title: row.usage_count for row in response.context["object_list"]
        }
        self.assertEqual(by_title["Used"], 1)
        self.assertEqual(by_title["Unused"], 0)

    def test_deleting_user_item_preserves_global_item(self):
        item = Item.objects.create(title="Shared", media_type=Item.MediaType.GAME)
        user_item = UserItem.objects.create(user=self.user, item=item)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("useritem_delete", kwargs={"pk": user_item.pk})
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(UserItem.objects.filter(pk=user_item.pk).exists())
        self.assertTrue(Item.objects.filter(pk=item.pk).exists())

    def test_suggestions_requires_login(self):
        response = self.client.get(
            reverse("useritem_item_suggestions"),
            {"q": "du"},
        )
        self.assertEqual(response.status_code, 302)

    def test_suggestions_filter_by_query_and_media_type(self):
        Item.objects.create(title="Dune", media_type=Item.MediaType.BOOK)
        Item.objects.create(title="Dune", media_type=Item.MediaType.MOVIE)
        Item.objects.create(title="Mistborn", media_type=Item.MediaType.BOOK)
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("useritem_item_suggestions"),
            {"q": "du", "media_type": Item.MediaType.BOOK},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["title"], "Dune")
        self.assertEqual(payload["results"][0]["media_type"], Item.MediaType.BOOK)

    def test_suggestions_return_empty_without_media_type(self):
        Item.objects.create(title="Dune", media_type=Item.MediaType.BOOK)
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("useritem_item_suggestions"),
            {"q": "du"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])
