from django.contrib import admin
from .models import (
    Bookmark,
    Collection,
    CollectionItem,
    InferenceRequest,
    MediaAsset,
    Star,
)


@admin.register(InferenceRequest)
class InferenceRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "inference_type",
        "status",
        "visibility",
        "star_count",
        "created_on",
    )
    list_filter = ("inference_type", "status", "visibility", "created_on")
    readonly_fields = ("created_on", "modified_on", "share_token", "star_count")
    search_fields = ("user__username", "payload")


@admin.register(Star)
class StarAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "request", "created_on")
    readonly_fields = ("created_on", "modified_on")


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "request", "created_on")
    readonly_fields = ("created_on", "modified_on")


class CollectionItemInline(admin.TabularInline):
    model = CollectionItem
    extra = 0
    raw_id_fields = ("request",)


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "name", "slug", "visibility", "created_on")
    list_filter = ("visibility", "created_on")
    readonly_fields = ("created_on", "modified_on")
    search_fields = ("user__username", "name", "slug")
    inlines = [CollectionItemInline]


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "kind", "content_type", "size_bytes", "created_on")
    list_filter = ("kind", "created_on")
    readonly_fields = ("created_on", "modified_on")
    search_fields = ("user__username",)
