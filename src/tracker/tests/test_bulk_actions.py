from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from tracker.actions.bulk import BulkAssignToBucket
from tracker.models import TimeBucket, TimeBucketAssignment, TimeLayout, UserItem


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
class BulkAssignToBucketTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="bulk",
        )
        self.layout = TimeLayout.objects.create(user=self.user, name="Balance")
        self.bucket = TimeBucket.objects.create(layout=self.layout, name="Work")
        self.item_a = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Item A",
        )
        self.item_b = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Item B",
        )

    def test_bulk_assign_to_bucket(self):
        action = BulkAssignToBucket()
        qs = UserItem.objects.filter(user=self.user)
        payload = action(qs, layout=self.layout, bucket=self.bucket)

        self.assertEqual(
            TimeBucketAssignment.objects.filter(
                layout=self.layout,
                bucket=self.bucket,
            ).count(),
            2,
        )
        self.assertIn("Assigned 2 item(s)", payload["title"])
