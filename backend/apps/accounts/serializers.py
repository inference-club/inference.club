from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):

    github_login = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "email",
            "is_staff",
            "is_active",
            "is_superuser",
            "profile_setup_complete",
            "github_login",
        )

    def get_github_login(self, obj) -> str | None:
        # social_django's reverse manager. Only one GitHub social_auth row
        # per user in practice; iterate so prefetch_related kicks in if a
        # caller adds it.
        for sa in obj.social_auth.all():
            if sa.provider == "github":
                return (sa.extra_data or {}).get("login") or None
        return None
