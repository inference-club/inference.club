from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .models import AccessCode, AccessPolicy

User = get_user_model()


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """Email-based user admin (this project removed ``username``)."""

    ordering = ("email",)
    list_display = (
        "email",
        "handle",
        "account_type",
        "is_staff",
        "is_superuser",
        "is_active",
        "date_joined",
    )
    list_filter = ("account_type", "is_staff", "is_superuser", "is_active")
    search_fields = ("email", "handle", "anon_alias")
    readonly_fields = ("date_joined", "last_login", "session_epoch")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Identity",
            {
                "fields": (
                    "account_type",
                    "handle",
                    "anon_alias",
                    "use_anon_alias",
                    "alias_regenerated_at",
                    "session_epoch",
                )
            },
        ),
        (
            "Profile",
            {
                "fields": (
                    "profile_setup_complete",
                    "routing_preference",
                    "default_request_visibility",
                    "public_profile_enabled",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "is_staff", "is_superuser"),
            },
        ),
    )


@admin.register(AccessCode)
class AccessCodeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "label",
        "user",
        "is_active",
        "expires_at",
        "last_used_at",
        "use_count",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "label", "user__handle", "user__email")
    readonly_fields = ("created_at", "last_used_at", "use_count")


@admin.register(AccessPolicy)
class AccessPolicyAdmin(admin.ModelAdmin):
    """Singleton — the in-app /dashboard/admin/access page is the primary UI;
    this is the belt-and-braces fallback."""

    def has_add_permission(self, request):
        # get_or_create via AccessPolicy.load(); never two rows.
        return not AccessPolicy.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
