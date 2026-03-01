from django.contrib import admin
from django import forms
from django.db.models import QuerySet

from .models import Item, UserItem, UserItemHistory, Tag, Queue, Profile, SavedFilter


@admin.action(description="Mark selected UserItems as completed")
def mark_completed(modeladmin, request, queryset):
    from .models import UserItemHistory

    history = [
        UserItemHistory(user_item=ui, event_type=UserItemHistory.Event.COMPLETED)
        for ui in queryset
    ]
    UserItemHistory.objects.bulk_create(history)
    queryset.update(shelf=UserItem.Shelf.DONE)


@admin.action(description="Mark selected UserItem as revisited")
def mark_revisited(modeladmin, request, queryset):
    from .models import UserItemHistory

    history = [
        UserItemHistory(user_item=ui, event_type=UserItemHistory.Event.REVISITED)
        for ui in queryset
    ]
    UserItemHistory.objects.bulk_create(history)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("title", "media_type", "created_at", "updated_at")
    search_fields = ("title", "media_type")


# --------------
# UserItem admin
# --------------


class SavedFilterListFilter(admin.SimpleListFilter):
    title = "Saved filter"
    parameter_name = "sf"  # querystring key: ?sf?<id>

    def lookups(self, request, model_admin):
        # Only show filters owned by the logged-in user
        return [(str(sf.pk), sf.name) for sf in request.user.saved_filters.all()]

    def queryset(self, request, queryset: QuerySet):
        sf_id = self.value()
        if not sf_id:
            return queryset

        sf = (
            SavedFilter.objects.filter(pk=sf_id, user=request.user)
            .only("id", "definition", "user")
            .first()
        )

        if not sf:
            return queryset

        # Apply my custom queryset logic
        qs = queryset.filter(sf.as_q())

        # If tags are in play, avoid duplicates due to M2M joins
        d = sf.definition or {}
        if d.get("tags"):
            qs = qs.distinct()

        return qs


class UserItemAdminForm(forms.ModelForm):
    class Meta:
        model = UserItem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        # Restrict tag choices to logged-in user
        if request is not None:
            self.fields["tags"].queryset = Tag.objects.filter(user=request.user)
        else:
            self.fields["tags"].queryset = Tag.objects.none()


@admin.register(UserItem)
class UserItemAdmin(admin.ModelAdmin):
    form = UserItemAdminForm

    list_display = (
        "user",
        "display_title",
        "is_project",
        "shelf",
        "tag_list",
        "last_revisited",
        "last_completed",
        "created_at",
        "created_by",
    )
    search_fields = (
        "item__title",
        "title_override",
    )
    list_filter = (
        SavedFilterListFilter,
        "shelf",
        "is_project",
    )
    autocomplete_fields = (
        "item",
        "tags",
    )
    actions = (mark_completed, mark_revisited)

    def get_queryset(self, request):
        qs = (
            super()
            .get_queryset(request)
            .filter(user=request.user)
            .prefetch_related("tags")
            .with_latest_dates()
            .order_by("last_revisited_at")
        )

        return qs

    @admin.display(description="Last revisited", ordering="last_revisited_at")
    def last_revisited(self, obj):
        return obj.last_revisited_at

    @admin.display(description="Last completed", ordering="last_completed_at")
    def last_completed(self, obj):
        return obj.last_completed_at

    @admin.display(description="Tags")
    def tag_list(self, obj):
        return ", ".join(t.name for t in obj.tags.all())

    def get_form(self, request, obj=None, change=False, **kwargs):
        """
        Wrap the admin form class so it always receives request=...
        """
        form_class = super().get_form(request, obj, change=change, **kwargs)

        class RequestInjectedForm(form_class):
            def __init__(self, *args, **kw):
                kw["request"] = request
                super().__init__(*args, **kw)

        return RequestInjectedForm

    def get_readonly_fields(self, request, obj=None):
        # Prevent accidental editing even if the field is shown somewhere
        return tuple(super().get_readonly_fields(request, obj)) + ("user", "created_by")

    def save_model(self, request, obj, form, change):
        # Enforce per-user ownership always
        obj.user = request.user
        if not change or obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """
        Extra safety: even if form changes, tags dropdown stays user-scoped
        """
        if db_field.name == "tags":
            kwargs["queryset"] = Tag.objects.filter(user=request.user)

        return super().formfield_for_manytomany(db_field, request, **kwargs)


@admin.register(UserItemHistory)
class UserItemHistoryAdmin(admin.ModelAdmin):
    list_display = ("user_item", "happened_at", "event_type")
    search_fields = ("user_item", "event_type")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "user")
    search_fields = ("name",)

    # Restrict view to logged-in user
    def get_queryset(self, request):
        qs = super().get_queryset(request)

        return qs.filter(user=request.user)

    # Always bind saves to logged-in user
    def save_model(self, request, obj, form, change):
        obj.user = request.user
        super().save_model(request, obj, form, change)


@admin.register(Queue)
class QueueAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "position")
    list_editable = ("position",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "date_format")
    list_select_related = ("user",)
    raw_id_fields = ("user",)


@admin.register(SavedFilter)
class SavedFilterAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "definition")
    list_select_related = ("user",)
    raw_id_fields = ("user",)
