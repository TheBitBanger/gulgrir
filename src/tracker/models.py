from django.conf import settings
from django.db import models, transaction
from django.db.models import JSONField, OuterRef, Q, Subquery
from django.db.models.functions import Lower
from django.utils import timezone
from pytz import common_timezones


class Item(models.Model):
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


    def __str__(self):
        return self.title


class UserItemQuerySet(models.QuerySet):
    def record_event(self, event: "UserItemHistory.Event") -> int:
        """
        Bulk-create one UserItemHistory row per item and, for COMPLETED, move the shelf to DONE. Returns the number of affected items.
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

    def with_latest_dates(self):
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

        return self.annotate(
            last_completed_at=Subquery(latest_completed),
            last_revisited_at=Subquery(latest_revisited),
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

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    item = models.ForeignKey(
        Item, null=True, blank=True, on_delete=models.CASCADE
    )  # Null UserItems are actually projects, they won't have an Item entry
    is_project = models.BooleanField(default=False)
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
    tags = models.ManyToManyField("Tag", blank=True, related_name="user_items")

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
    class Event(models.TextChoices):
        COMPLETED = "completed", "Completed"
        REVISITED = "revisited", "Revisited"

    user_item = models.ForeignKey(
        UserItem, on_delete=models.CASCADE, related_name="history"
    )
    happened_at = models.DateTimeField(default=timezone.now, blank=True)
    event_type = models.CharField(max_length=20, choices=Event.choices)


class Tag(models.Model):
    """Per-user free-form tags that can be attached to UserItems only."""

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


class Queue(models.Model):
    """
    A saved filter + ordering definition (JSON DSL) that is evaluated at read
    time.
    Example filter JSON:
        {
            "media_type": ["game"],
            "is_project": false,
            "tags": ["replayable"],
            "title_override__not_null": true
        }
    Example ordering JSON:
        { "field": "created_at", "direction": "asc" }
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="queues"
    )
    name = models.CharField(max_length=64)
    filter_definition = JSONField(default=dict, blank=True)
    ordering_definition = JSONField(default=dict, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("user", "name")
        ordering = ("position",)

    def __str__(self):
        return self.name

    # helper API used by the views
    def as_q(self) -> Q:
        """
        Translate the sored filter_definition into a Django Q object.
        Supported keys:
            media_type: list[str]
            is_project: bool
            title_override__not_null: bool
            tags: list[str]
        """
        fd = self.filter_definition or {}
        q = Q(user=self.user)

        if "media_type" in fd:
            q &= Q(item__media_type__in=fd["media_type"])
        if "is_project" in fd:
            q &= Q(is_project=fd["is_project"])
        if fd.get("title_override__not_null"):
            q &= ~Q(title_override__isnull=True)
        if "tags" in fd and fd["tags"]:
            q &= Q(tags__name__in=fd["tags"])
        if "shelf" in fd and fd["shelf"]:
            q &= Q(shelf__in=fd["shelf"])

        return q

    def ordering_clause(self) -> list[str]:
        od = self.ordering_definition or {}
        field = od.get("field", "created_at")
        direction = "" if od.get("direction", "asc") == "asc" else "-"

        return [f"{direction}{field}"]


class Profile(models.Model):
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
