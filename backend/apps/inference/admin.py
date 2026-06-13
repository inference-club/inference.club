from django.contrib import admin
from .models import (
    Bookmark,
    Collection,
    CollectionItem,
    ContentReport,
    InferenceRequest,
    MediaAsset,
    Provider,
    ProviderService,
    Star,
    VoiceSample,
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


@admin.register(VoiceSample)
class VoiceSampleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "speaker_name",
        "label",
        "is_default",
        "transcript_source",
        "created_on",
    )
    list_filter = ("is_default", "transcript_source", "created_on")
    readonly_fields = ("created_on", "modified_on")
    search_fields = ("user__username", "speaker_name", "transcript")
    raw_id_fields = ("audio",)


@admin.register(ContentReport)
class ContentReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "request",
        "reporter",
        "reason",
        "status",
        "resolved_by",
        "created_on",
    )
    list_filter = ("status", "reason", "created_on")
    readonly_fields = ("created_on", "modified_on", "resolved_at")
    raw_id_fields = ("request", "reporter", "resolved_by")
    search_fields = ("request__id", "reporter__email", "details")


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "name",
        "is_active",
        "accepting_requests",
        "last_seen_at",
        "created_on",
    )
    list_filter = ("is_active", "accepting_requests", "created_on")
    readonly_fields = ("created_on", "modified_on", "registered_at", "last_seen_at")
    search_fields = ("user__email", "name", "tailnet_hostname")


@admin.register(ProviderService)
class ProviderServiceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "provider",
        "name",
        "service_type",
        "access_policy",
        "is_active",
    )
    list_filter = ("service_type", "access_policy", "is_active")
    readonly_fields = ("created_on", "modified_on")
    search_fields = ("provider__name", "name")
