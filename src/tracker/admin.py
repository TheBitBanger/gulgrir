from django.contrib import admin

from .models import Item


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("title", "media_type", "created_at", "updated_at")
    search_fields = ("title", "media_type")
