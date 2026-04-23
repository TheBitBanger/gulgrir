from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from tracker.models import Item, UserItem


class UserItemPinTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="pin-user",
            email="pin@example.com",
        )
        self.item = Item.objects.create(media_type=Item.MediaType.BOOK, title="Pin")
        self.user_item = UserItem.objects.create(user=self.user, item=self.item)

    def test_pin_user_item(self):
        self.client.force_login(self.user)
        url = reverse("useritem_pin", args=[self.user_item.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.user_item.refresh_from_db()
        self.assertTrue(self.user_item.is_pinned)

    def test_unpin_user_item(self):
        self.user_item.is_pinned = True
        self.user_item.save(update_fields=["is_pinned"])
        self.client.force_login(self.user)
        url = reverse("useritem_unpin", args=[self.user_item.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.user_item.refresh_from_db()
        self.assertFalse(self.user_item.is_pinned)
