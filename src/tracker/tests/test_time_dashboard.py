from datetime import time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tracker.models import TimeBucket, TimeBucketAssignment, TimeLayout, UserItem
from tracker.services.time_dashboard import build_chart_entries
from tracker.services.time_windows import build_time_windows, day_range


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    }
)
class TimeDashboardAssignmentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dashboard",
        )
        self.layout = TimeLayout.objects.create(user=self.user, name="Balance")
        self.bucket_work = TimeBucket.objects.create(
            layout=self.layout,
            name="Work",
        )
        self.bucket_play = TimeBucket.objects.create(
            layout=self.layout,
            name="Play",
        )
        self.item_work = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Work item",
        )
        self.item_unassigned = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Unassigned item",
        )
        self.item_ignored = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Ignored item",
        )

        TimeBucketAssignment.objects.create(
            layout=self.layout,
            user_item=self.item_work,
            bucket=self.bucket_work,
        )
        TimeBucketAssignment.objects.create(
            layout=self.layout,
            user_item=self.item_ignored,
            is_ignored=True,
        )

    def test_build_chart_entries_bucket_priority(self):
        durations = {
            self.item_work.id: int(timedelta(hours=1).total_seconds()),
            self.item_unassigned.id: int(timedelta(minutes=30).total_seconds()),
            self.item_ignored.id: int(timedelta(minutes=20).total_seconds()),
        }
        user_items = {
            self.item_work.id: self.item_work,
            self.item_unassigned.id: self.item_unassigned,
            self.item_ignored.id: self.item_ignored,
        }
        assignments = {
            a.user_item_id: a
            for a in TimeBucketAssignment.objects.filter(layout=self.layout)
        }
        buckets = list(TimeBucket.objects.filter(layout=self.layout))

        result = build_chart_entries(
            layout=self.layout,
            buckets=buckets,
            assignments=assignments,
            item_durations=durations,
            user_items=user_items,
            bucket_id=None,
            include_zero_time=True,
        )

        def collect_names(nodes: list[dict[str, object]]) -> list[str]:
            names: list[str] = []
            for node in nodes:
                names.append(str(node["name"]))
                names.extend(collect_names(node.get("children", [])))
            return names

        bucket_names = collect_names(result["bucket_tree"])
        self.assertIn("Work", bucket_names)
        self.assertIn("Play", bucket_names)
        self.assertEqual(len(result["ignored_items"]), 1)
        self.assertEqual(len(result["unassigned_items"]), 1)

    def test_build_chart_entries_tree_rollup_and_items(self):
        bucket_projects = TimeBucket.objects.create(
            layout=self.layout,
            name="Projects",
            parent=self.bucket_work,
        )
        bucket_coding = TimeBucket.objects.create(
            layout=self.layout,
            name="Coding",
            parent=bucket_projects,
        )
        item_deep = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Deep item",
        )
        item_zero = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Zero item",
        )
        item_play = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Play item",
        )
        TimeBucketAssignment.objects.create(
            layout=self.layout,
            user_item=item_deep,
            bucket=bucket_coding,
        )
        TimeBucketAssignment.objects.create(
            layout=self.layout,
            user_item=item_zero,
            bucket=bucket_projects,
        )
        TimeBucketAssignment.objects.create(
            layout=self.layout,
            user_item=item_play,
            bucket=self.bucket_play,
        )
        durations = {
            item_deep.id: int(timedelta(hours=2).total_seconds()),
            item_zero.id: 0,
            item_play.id: int(timedelta(minutes=45).total_seconds()),
        }
        user_items = {
            item_deep.id: item_deep,
            item_zero.id: item_zero,
            item_play.id: item_play,
        }
        assignments = {
            a.user_item_id: a
            for a in TimeBucketAssignment.objects.filter(layout=self.layout)
        }
        buckets = list(TimeBucket.objects.filter(layout=self.layout))

        def find_node(
            nodes: list[dict[str, object]], name: str
        ) -> dict[str, object] | None:
            for node in nodes:
                if node["name"] == name:
                    return node
                child = find_node(node.get("children", []), name)
                if child is not None:
                    return child
            return None

        result = build_chart_entries(
            layout=self.layout,
            buckets=buckets,
            assignments=assignments,
            item_durations=durations,
            user_items=user_items,
            bucket_id=None,
            include_zero_time=False,
        )
        work_node = find_node(result["bucket_tree"], "Work")
        projects_node = find_node(result["bucket_tree"], "Projects")
        coding_node = find_node(result["bucket_tree"], "Coding")
        play_node = find_node(result["bucket_tree"], "Play")

        self.assertIsNotNone(work_node)
        self.assertIsNotNone(projects_node)
        self.assertIsNotNone(coding_node)
        self.assertIsNotNone(play_node)
        self.assertEqual(work_node["seconds"], durations[item_deep.id])
        self.assertEqual(projects_node["seconds"], durations[item_deep.id])
        self.assertEqual(coding_node["seconds"], durations[item_deep.id])
        self.assertEqual(play_node["seconds"], durations[item_play.id])
        self.assertEqual(work_node["bucket_share_percent"], 72)
        self.assertEqual(play_node["bucket_share_percent"], 27)
        self.assertEqual(len(coding_node["items"]), 1)
        self.assertEqual(coding_node["items"][0]["item_id"], item_deep.id)
        self.assertEqual(coding_node["items"][0]["item_share_percent"], 100)
        self.assertEqual(len(projects_node["items"]), 0)

        result_with_zero = build_chart_entries(
            layout=self.layout,
            buckets=buckets,
            assignments=assignments,
            item_durations=durations,
            user_items=user_items,
            bucket_id=None,
            include_zero_time=True,
        )
        projects_node = find_node(result_with_zero["bucket_tree"], "Projects")
        self.assertIsNotNone(projects_node)
        self.assertEqual(len(projects_node["items"]), 1)
        self.assertEqual(projects_node["items"][0]["item_id"], item_zero.id)
        self.assertEqual(projects_node["items"][0]["item_share_percent"], 0)

    def test_build_chart_entries_selected_bucket_tree(self):
        bucket_projects = TimeBucket.objects.create(
            layout=self.layout,
            name="Projects",
            parent=self.bucket_work,
        )
        bucket_coding = TimeBucket.objects.create(
            layout=self.layout,
            name="Coding",
            parent=bucket_projects,
        )
        item_deep = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Deep item",
        )
        TimeBucketAssignment.objects.create(
            layout=self.layout,
            user_item=item_deep,
            bucket=bucket_coding,
        )
        durations = {item_deep.id: int(timedelta(hours=1).total_seconds())}
        user_items = {item_deep.id: item_deep}
        assignments = {
            a.user_item_id: a
            for a in TimeBucketAssignment.objects.filter(layout=self.layout)
        }
        buckets = list(TimeBucket.objects.filter(layout=self.layout))

        result = build_chart_entries(
            layout=self.layout,
            buckets=buckets,
            assignments=assignments,
            item_durations=durations,
            user_items=user_items,
            bucket_id=bucket_projects.id,
            include_zero_time=False,
        )

        self.assertEqual(len(result["bucket_tree"]), 1)
        self.assertEqual(result["bucket_tree"][0]["name"], "Projects")
        self.assertEqual(result["bucket_tree"][0]["bucket_share_percent"], 100)

    def test_build_chart_entries_sorting(self):
        item_play = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Play item",
        )
        item_alpha = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Alpha task",
        )
        item_beta = UserItem.objects.create(
            user=self.user,
            is_project=True,
            title_override="Beta task",
        )
        TimeBucketAssignment.objects.create(
            layout=self.layout,
            user_item=item_play,
            bucket=self.bucket_play,
        )
        TimeBucketAssignment.objects.create(
            layout=self.layout,
            user_item=item_alpha,
            bucket=self.bucket_work,
        )
        TimeBucketAssignment.objects.create(
            layout=self.layout,
            user_item=item_beta,
            bucket=self.bucket_work,
        )
        durations = {
            self.item_work.id: int(timedelta(minutes=40).total_seconds()),
            item_play.id: int(timedelta(minutes=20).total_seconds()),
            item_alpha.id: int(timedelta(minutes=10).total_seconds()),
            item_beta.id: int(timedelta(minutes=10).total_seconds()),
        }
        user_items = {
            self.item_work.id: self.item_work,
            item_play.id: item_play,
            item_alpha.id: item_alpha,
            item_beta.id: item_beta,
        }
        assignments = {
            a.user_item_id: a
            for a in TimeBucketAssignment.objects.filter(layout=self.layout)
        }
        buckets = list(TimeBucket.objects.filter(layout=self.layout))

        def find_node(
            nodes: list[dict[str, object]], name: str
        ) -> dict[str, object] | None:
            for node in nodes:
                if node["name"] == name:
                    return node
                child = find_node(node.get("children", []), name)
                if child is not None:
                    return child
            return None

        result_desc = build_chart_entries(
            layout=self.layout,
            buckets=buckets,
            assignments=assignments,
            item_durations=durations,
            user_items=user_items,
            bucket_id=None,
            include_zero_time=True,
            sort_dir="desc",
        )
        bucket_names_desc = [node["name"] for node in result_desc["bucket_tree"]]
        self.assertEqual(bucket_names_desc[:2], ["Work", "Play"])
        work_node_desc = find_node(result_desc["bucket_tree"], "Work")
        self.assertIsNotNone(work_node_desc)
        work_item_titles_desc = [item["title"] for item in work_node_desc["items"]]
        self.assertEqual(
            work_item_titles_desc[:3],
            [
                "Work item",
                "Alpha task",
                "Beta task",
            ],
        )

        result_asc = build_chart_entries(
            layout=self.layout,
            buckets=buckets,
            assignments=assignments,
            item_durations=durations,
            user_items=user_items,
            bucket_id=None,
            include_zero_time=True,
            sort_dir="asc",
        )
        bucket_names_asc = [node["name"] for node in result_asc["bucket_tree"]]
        self.assertEqual(bucket_names_asc[:2], ["Play", "Work"])
        work_node_asc = find_node(result_asc["bucket_tree"], "Work")
        self.assertIsNotNone(work_node_asc)
        work_item_titles_asc = [item["title"] for item in work_node_asc["items"]]
        self.assertEqual(
            work_item_titles_asc[:3],
            [
                "Alpha task",
                "Beta task",
                "Work item",
            ],
        )

    def test_ignore_assignment_clears_bucket(self):
        self.client.force_login(self.user)
        url = reverse("time_assignment_update")
        payload = {
            "layout_id": self.layout.id,
            "item_id": self.item_work.id,
            "action": "ignore",
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        assignment = TimeBucketAssignment.objects.get(
            layout=self.layout,
            user_item=self.item_work,
        )
        self.assertTrue(assignment.is_ignored)
        self.assertIsNone(assignment.bucket)

    def test_assign_unignores(self):
        self.client.force_login(self.user)
        url = reverse("time_assignment_update")
        payload = {
            "layout_id": self.layout.id,
            "item_id": self.item_ignored.id,
            "action": "assign",
            "bucket_id": self.bucket_play.id,
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        assignment = TimeBucketAssignment.objects.get(
            layout=self.layout,
            user_item=self.item_ignored,
        )
        self.assertFalse(assignment.is_ignored)
        self.assertEqual(assignment.bucket, self.bucket_play)

    def test_unassign_clears_bucket(self):
        self.client.force_login(self.user)
        url = reverse("time_assignment_update")
        payload = {
            "layout_id": self.layout.id,
            "item_id": self.item_work.id,
            "action": "unassign",
        }
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        assignment = TimeBucketAssignment.objects.get(
            layout=self.layout,
            user_item=self.item_work,
        )
        self.assertFalse(assignment.is_ignored)
        self.assertIsNone(assignment.bucket)

    def test_time_settings_shows_assigned_items(self):
        self.client.force_login(self.user)
        url = f"{reverse('time_settings')}?layout={self.layout.id}"
        response = self.client.get(url)
        self.assertContains(response, "Work item")

    def test_time_dashboard_lists_assigned_items_with_no_time(self):
        TimeBucketAssignment.objects.create(
            layout=self.layout,
            user_item=self.item_unassigned,
            bucket=self.bucket_work,
        )
        self.client.force_login(self.user)
        url = (
            f"{reverse('time_dashboard')}?layout={self.layout.id}"
            f"&bucket={self.bucket_work.id}&show_zero=1"
        )
        response = self.client.get(url)
        self.assertContains(response, "Unassigned item")

    @patch("tracker.services.time_selection.random.choices")
    def test_time_level_select_returns_bucket(self, mock_choices):
        child = TimeBucket.objects.create(
            layout=self.layout,
            name="Child",
            parent=self.bucket_work,
        )
        TimeBucketAssignment.objects.create(
            layout=self.layout,
            user_item=self.item_unassigned,
            bucket=self.bucket_work,
        )
        mock_choices.side_effect = lambda entries, weights, k: [entries[0]]

        self.client.force_login(self.user)
        url = reverse("time_level_select")
        payload = {
            "layout_id": self.layout.id,
            "bucket_id": self.bucket_work.id,
            "time_window": "all_time",
        }
        response = self.client.post(url, payload, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["kind"], "bucket")
        self.assertIn(f"bucket={child.id}", data["url"])

    def test_update_layout(self):
        self.client.force_login(self.user)
        url = reverse("time_layout_update")
        payload = {
            "layout_id": self.layout.id,
            "layout_name": "Balance updated",
            "layout_description": "New desc",
        }
        response = self.client.post(url, payload, follow=True)
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.name, "Balance updated")
        self.assertEqual(self.layout.description, "New desc")
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Layout updated.", messages)

    def test_delete_layout(self):
        self.client.force_login(self.user)
        url = reverse("time_layout_delete")
        response = self.client.post(url, {"layout_id": self.layout.id}, follow=True)
        self.assertFalse(TimeLayout.objects.filter(id=self.layout.id).exists())
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Layout deleted.", messages)

    def test_update_bucket(self):
        self.client.force_login(self.user)
        url = reverse("time_bucket_update")
        payload = {
            "layout_id": self.layout.id,
            "bucket_id": self.bucket_work.id,
            "bucket_name": "Work updated",
            "parent_id": "",
        }
        response = self.client.post(url, payload, follow=True)
        self.bucket_work.refresh_from_db()
        self.assertEqual(self.bucket_work.name, "Work updated")
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Bucket updated.", messages)

    def test_reparent_bucket(self):
        self.client.force_login(self.user)
        url = reverse("time_bucket_update")
        payload = {
            "layout_id": self.layout.id,
            "bucket_id": self.bucket_play.id,
            "bucket_name": self.bucket_play.name,
            "parent_id": self.bucket_work.id,
        }
        response = self.client.post(url, payload, follow=True)
        self.bucket_play.refresh_from_db()
        self.assertEqual(self.bucket_play.parent, self.bucket_work)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Bucket updated.", messages)

    def test_reparent_bucket_cycle_error(self):
        child = TimeBucket.objects.create(
            layout=self.layout,
            name="Child",
            parent=self.bucket_work,
        )
        self.client.force_login(self.user)
        url = reverse("time_bucket_update")
        payload = {
            "layout_id": self.layout.id,
            "bucket_id": self.bucket_work.id,
            "bucket_name": self.bucket_work.name,
            "parent_id": child.id,
        }
        response = self.client.post(url, payload, follow=True)
        self.bucket_work.refresh_from_db()
        self.assertIsNone(self.bucket_work.parent)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Bucket cannot be moved under its descendant.", messages)

    def test_delete_bucket_promote_children(self):
        child = TimeBucket.objects.create(
            layout=self.layout,
            name="Child",
            parent=self.bucket_work,
        )
        self.client.force_login(self.user)
        url = reverse("time_bucket_delete")
        payload = {
            "layout_id": self.layout.id,
            "bucket_id": self.bucket_work.id,
            "delete_mode": "promote",
        }
        response = self.client.post(url, payload, follow=True)
        self.assertFalse(TimeBucket.objects.filter(id=self.bucket_work.id).exists())
        child.refresh_from_db()
        self.assertIsNone(child.parent)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Bucket deleted and children promoted.", messages)

    def test_delete_bucket_cascade(self):
        child = TimeBucket.objects.create(
            layout=self.layout,
            name="Child",
            parent=self.bucket_work,
        )
        self.client.force_login(self.user)
        url = reverse("time_bucket_delete")
        payload = {
            "layout_id": self.layout.id,
            "bucket_id": self.bucket_work.id,
            "delete_mode": "cascade",
        }
        response = self.client.post(url, payload, follow=True)
        self.assertFalse(TimeBucket.objects.filter(id=self.bucket_work.id).exists())
        self.assertFalse(TimeBucket.objects.filter(id=child.id).exists())
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Bucket and its children deleted.", messages)


class TimeWindowCalendarTests(TestCase):
    def test_day_range_respects_cutoff(self):
        tz = timezone.get_current_timezone()
        cutoff = time(4, 0)
        start, end = day_range(timezone.localdate(), cutoff)
        self.assertEqual(start.tzinfo, tz)
        self.assertEqual(start.time(), cutoff)
        self.assertEqual(end - start, timedelta(days=1))

    def test_last_7_days_uses_calendar_bounds(self):
        tz = timezone.get_current_timezone()
        now = timezone.make_aware(
            timezone.datetime(2025, 5, 19, 15, 30, 0),
            tz,
        )
        windows = build_time_windows(now=now)
        last_7 = next(w for w in windows if w.key == "last_7")
        today = timezone.localdate(now)
        expected_start, _ = day_range(today - timedelta(days=6))
        _, expected_end = day_range(today)
        self.assertEqual(last_7.start, expected_start)
        self.assertEqual(last_7.end, expected_end)

    def test_today_and_yesterday_windows(self):
        tz = timezone.get_current_timezone()
        now = timezone.make_aware(
            timezone.datetime(2025, 5, 19, 9, 0, 0),
            tz,
        )
        windows = build_time_windows(now=now)
        today_window = next(w for w in windows if w.key == "today")
        yesterday_window = next(w for w in windows if w.key == "yesterday")
        today = timezone.localdate(now)
        expected_today_start, expected_today_end = day_range(today)
        expected_yesterday_start, expected_yesterday_end = day_range(
            today - timedelta(days=1)
        )
        self.assertEqual(today_window.start, expected_today_start)
        self.assertEqual(today_window.end, expected_today_end)
        self.assertEqual(yesterday_window.start, expected_yesterday_start)
        self.assertEqual(yesterday_window.end, expected_yesterday_end)

    def test_cutoff_shifts_today_window(self):
        tz = timezone.get_current_timezone()
        cutoff = time(4, 0)
        now = timezone.make_aware(
            timezone.datetime(2025, 5, 19, 2, 0, 0),
            tz,
        )
        windows = build_time_windows(now=now, cutoff_time=cutoff)
        today_window = next(w for w in windows if w.key == "today")
        yesterday_window = next(w for w in windows if w.key == "yesterday")
        expected_today_start, expected_today_end = day_range(
            timezone.localdate(now) - timedelta(days=1),
            cutoff,
        )
        expected_yesterday_start, expected_yesterday_end = day_range(
            timezone.localdate(now) - timedelta(days=2),
            cutoff,
        )
        self.assertEqual(today_window.start, expected_today_start)
        self.assertEqual(today_window.end, expected_today_end)
        self.assertEqual(yesterday_window.start, expected_yesterday_start)
        self.assertEqual(yesterday_window.end, expected_yesterday_end)
