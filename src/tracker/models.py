from datetime import time
from typing import Any, cast
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import OuterRef, Q, Subquery
from django.db.models.functions import Lower
from django.utils import timezone
from pytz import common_timezones


class Item(models.Model):
    id: int

    class MediaType(models.TextChoices):
        BOOK = "book", "Book"
        MOVIE = "movie", "Movie"
        GAME = "game", "Game"
        MUSIC = "music", "Music"
        TV_SHOW = "show", "Show"
        ANIME = "anime", "Anime"
        OTHER = "other", "Other"
        LIGHT_NOVEL = "light_novel", "Light Novel"
        MANGA = "manga", "Manga"

    title = models.CharField(max_length=255)
    media_type = models.CharField(
        max_length=20, choices=MediaType.choices, default=MediaType.OTHER
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("title"),
                "media_type",
                name="uniq_item_lower_title_media_type",
            )
        ]

    def __str__(self):
        return self.title


class UserItemQuerySet(models.QuerySet["UserItem"]):
    def record_event(self, event: "UserItemHistory.Event") -> int:
        """
        Bulk-create one UserItemHistory row per item and, for COMPLETED,
        move the shelf to DONE. Returns the number of affected items.
        """
        # useritem doesn't exist - quit
        if not self.exists():
            return 0

        now = timezone.now()
        history_rows = [
            UserItemHistory(user_item=ui, event_type=event, happened_at=now)
            for ui in self
        ]
        with transaction.atomic():
            UserItemHistory.objects.bulk_create(history_rows)
            if event == UserItemHistory.Event.COMPLETED:
                self.update(shelf=UserItem.Shelf.DONE)

        return len(history_rows)

    def with_latest_dates(self) -> "UserItemQuerySet":
        """Annotate UserItem with last_completed_at / last_revisited_at."""
        latest_completed = (
            UserItemHistory.objects.filter(
                user_item=OuterRef("pk"), event_type=UserItemHistory.Event.COMPLETED
            )
            .order_by("-happened_at")
            .values("happened_at")[:1]
        )
        latest_revisited = (
            UserItemHistory.objects.filter(
                user_item=OuterRef("pk"), event_type=UserItemHistory.Event.REVISITED
            )
            .order_by("-happened_at")
            .values("happened_at")[:1]
        )

        return cast(
            UserItemQuerySet,
            self.annotate(
                last_completed_at=Subquery(latest_completed),
                last_revisited_at=Subquery(latest_revisited),
            ),
        )


class UserItem(models.Model):
    class Shelf(models.TextChoices):
        BACKLOG = "backlog", "Backlog"
        IN_PROGRESS = "in_progress", "In Progress"
        DONE = "done", "Done"

    class Tier(models.IntegerChoices):
        UNRATED = 0, "-"
        S = 1, "S"
        A = 2, "A"
        B = 3, "B"
        C = 4, "C"
        D = 5, "D"
        E = 6, "E"
        F = 7, "F"

    # custom manager to provide more methods
    objects = UserItemQuerySet.as_manager()

    id: int
    user_id: int
    item_id: int | None
    created_by_id: int | None
    history: models.Manager["UserItemHistory"]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    item = models.ForeignKey(
        Item, null=True, blank=True, on_delete=models.PROTECT
    )  # Null UserItems are actually projects, they won't have an Item entry
    is_project = models.BooleanField(default=False)
    is_redoing = models.BooleanField(default=False)
    is_endless = models.BooleanField(default=False)
    title_override = models.CharField(max_length=255, blank=True, null=True)

    shelf = models.CharField(
        max_length=20, choices=Shelf.choices, default=Shelf.BACKLOG
    )
    tier = models.PositiveSmallIntegerField(
        choices=Tier.choices,
        default=Tier.UNRATED,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="created_user_items",
        on_delete=models.SET_NULL,
        null=True,
    )
    tags: Any = models.ManyToManyField("Tag", blank=True, related_name="user_items")
    timer_started_at = models.DateTimeField(null=True, blank=True)
    is_pinned = models.BooleanField(default=False)

    @property
    def display_title(self) -> str:
        if self.is_project:
            return self.title_override or "(untitled project)"
        if self.item:
            return self.item.title

        return "(untitled)"

    def __str__(self):
        return self.title_override or (
            self.item.title if self.item else "Unnamed project"
        )


class UserItemHistory(models.Model):
    id: int
    user_item_id: int

    class Event(models.TextChoices):
        COMPLETED = "completed", "Completed"
        REVISITED = "revisited", "Revisited"

    user_item = models.ForeignKey(
        UserItem, on_delete=models.CASCADE, related_name="history"
    )
    happened_at = models.DateTimeField(default=timezone.now, blank=True)
    event_type = models.CharField(max_length=20, choices=Event.choices)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.started_at and self.ended_at:
            self.duration = self.ended_at - self.started_at
        else:
            self.duration = None
        return super().save(*args, **kwargs)


class Tag(models.Model):
    """Per-user free-form tags that can be attached to UserItems only."""

    id: int
    user_id: int

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tags"
    )
    name = models.CharField(max_length=64)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "user",
                name="uniq_tag_user_lower_name",
            ),
        ]

    def __str__(self):
        return self.name


class Profile(models.Model):
    id: int
    user_id: int

    class Theme(models.TextChoices):
        SYSTEM = "system", "System"
        LIGHT = "light", "Light"
        DARK = "dark", "Dark"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    theme = models.CharField(
        max_length=16,
        choices=Theme.choices,
        default=Theme.SYSTEM,
    )
    date_format = models.CharField(
        max_length=32,
        default="%d/%m/%Y",
        help_text="Preferred display format for dates",
    )
    timezone = models.CharField(
        max_length=32,
        default="America/Mexico_City",
        choices=[(z, z) for z in common_timezones],
    )
    time_dashboard_mode = models.CharField(
        max_length=16,
        default="",
        blank=True,
    )
    time_dashboard_window_key = models.CharField(
        max_length=32,
        default="",
        blank=True,
    )
    time_dashboard_range_start = models.DateField(null=True, blank=True)
    time_dashboard_range_end = models.DateField(null=True, blank=True)
    time_dashboard_expand_depth = models.PositiveSmallIntegerField(default=3)
    time_dashboard_sort_dir = models.CharField(max_length=4, default="desc")
    time_dashboard_day_cutoff = models.TimeField(default=time(0, 0))
    time_default_layout = models.ForeignKey(
        "TimeLayout",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="default_for_profiles",
    )
    focus_default_target_minutes = models.PositiveIntegerField(default=720)
    focus_default_overflow_soft_cap_minutes = models.PositiveIntegerField(default=300)

    def flatpickr_format(self):
        # convert a few common strftime tokens to flatpickr
        return self.date_format.replace("%d", "d").replace("%m", "m").replace("%Y", "Y")

    def __str__(self):
        return f"Profile({self.user})"


class SavedFilter(models.Model):
    """
    A named, per-user set of filter criteria to be applied to UserItem list.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_filters"
    )
    name = models.CharField(max_length=64)
    definition = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "name")
        ordering = ("name",)

    def as_q(self) -> Q:
        """
        Translate stored dict -> Django Q
        """
        d = self.definition or {}
        q = Q(user=self.user)

        if "shelf" in d and d["shelf"]:
            q &= Q(shelf__in=d["shelf"])
        if "media_type" in d and d["media_type"]:
            q &= Q(item__media_type__in=d["media_type"])
        if d.get("is_project") is True:
            q &= Q(is_project=True)
        if "tags" in d and d["tags"]:
            q &= Q(tags__id__in=d["tags"])
        if "title_icontains" in d:
            q &= Q(item__title__icontains=d["title_icontains"]) | Q(
                title_override__icontains=d["title_icontains"]
            )
        if "tier" in d and d["tier"]:
            q &= Q(tier__in=d["tier"])

        return q

    def summary(self) -> str:
        d = self.definition or {}
        parts: list[str] = []

        shelf_values = d.get("shelf") or []
        if shelf_values:
            shelf_map = {value: label for value, label in UserItem.Shelf.choices}
            shelf_labels = [str(shelf_map.get(value, value)) for value in shelf_values]
            parts.append(f"Shelf={', '.join(shelf_labels)}")

        media_values = d.get("media_type") or []
        if media_values:
            media_map = {value: label for value, label in Item.MediaType.choices}
            media_labels = [str(media_map.get(value, value)) for value in media_values]
            parts.append(f"Media={', '.join(media_labels)}")

        tag_ids = d.get("tags") or []
        if tag_ids:
            tag_map = {
                tag_id: name
                for tag_id, name in Tag.objects.filter(
                    user=self.user, id__in=tag_ids
                ).values_list("id", "name")
            }
            tag_names = [tag_map.get(tag_id, str(tag_id)) for tag_id in tag_ids]
            parts.append(f"Tags={', '.join(tag_names)}")

        if d.get("title_icontains"):
            parts.append(f'Title~"{d["title_icontains"]}"')

        if d.get("is_project") is True:
            parts.append("Projects")

        tier_values = d.get("tier") or []
        if tier_values:
            tier_map = {value: label for value, label in UserItem.Tier.choices}
            tier_labels = [str(tier_map.get(value, value)) for value in tier_values]
            parts.append(f"Tier={', '.join(tier_labels)}")

        return " | ".join(parts) if parts else "All items"

    def query_params(self) -> str:
        d = self.definition or {}
        params: list[tuple[str, str]] = [("sf", str(self.pk))]

        for value in d.get("shelf") or []:
            params.append(("shelf", value))

        for value in d.get("media_type") or []:
            params.append(("media_type", value))

        if d.get("is_project") is True:
            params.append(("is_project", "on"))

        if d.get("title_icontains"):
            params.append(("title_icontains", d["title_icontains"]))

        for value in d.get("tags") or []:
            params.append(("tags", str(value)))

        for value in d.get("tier") or []:
            params.append(("tier", str(value)))

        return urlencode(params, doseq=True)


class TimeLayout(models.Model):
    id: int
    user_id: int

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="time_layouts",
    )
    name = models.CharField(max_length=64)
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("order", "name")
        unique_together = ("user", "name")

    def __str__(self):
        return f"{self.name}"


class TimeBucket(models.Model):
    id: int
    layout_id: int
    parent_id: int | None

    layout = models.ForeignKey(
        TimeLayout,
        on_delete=models.CASCADE,
        related_name="buckets",
    )
    name = models.CharField(max_length=64)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("order", "name")
        unique_together = ("layout", "parent", "name")

    def __str__(self):
        return f"{self.name}"


class TimeBucketAssignment(models.Model):
    class Mode(models.TextChoices):
        BUCKET = "bucket", "Bucket"
        TOP_LEVEL = "top_level", "Top level"
        IGNORED = "ignored", "Ignored"

    id: int
    layout_id: int
    user_item_id: int
    bucket_id: int | None

    layout = models.ForeignKey(
        TimeLayout,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    user_item = models.ForeignKey(
        UserItem,
        on_delete=models.CASCADE,
        related_name="time_assignments",
    )
    bucket = models.ForeignKey(
        TimeBucket,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assignments",
    )
    assignment_mode = models.CharField(
        max_length=16,
        choices=Mode.choices,
        default=Mode.BUCKET,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("layout", "user_item")

    def __str__(self):
        return f"{self.user_item} -> {self.bucket or 'Unassigned'}"


class FocusSprint(models.Model):
    class ScopeType(models.TextChoices):
        BUCKET = "bucket", "Bucket"
        ITEM = "item", "Item"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="focus_sprints",
    )
    scope_type = models.CharField(max_length=16, choices=ScopeType.choices)
    time_bucket = models.ForeignKey(
        TimeBucket,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="focus_sprints",
    )
    user_item = models.ForeignKey(
        UserItem,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="focus_sprints",
    )
    target_minutes = models.PositiveIntegerField(default=720)
    overflow_soft_cap_minutes = models.PositiveIntegerField(default=300)
    started_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-started_at",)

    def clean(self):
        bucket_set = self.time_bucket_id is not None
        item_set = self.user_item_id is not None
        if self.scope_type == self.ScopeType.BUCKET:
            if not bucket_set or item_set:
                raise ValidationError("Bucket scope requires only time_bucket.")
        elif self.scope_type == self.ScopeType.ITEM:
            if not item_set or bucket_set:
                raise ValidationError("Item scope requires only user_item.")
        if self.target_minutes <= 0:
            raise ValidationError("Target minutes must be positive.")
