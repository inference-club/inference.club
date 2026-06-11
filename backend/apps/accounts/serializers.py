from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.authtoken.models import Token

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):

    github_login = serializers.SerializerMethodField()
    api_token = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "email",
            "is_staff",
            "is_active",
            "is_superuser",
            "profile_setup_complete",
            "github_login",
            "api_token",
            "routing_preference",
            "default_request_visibility",
            "default_collection_name",
            "public_profile_enabled",
        )

    def get_api_token(self, obj) -> str:
        # Tokens are auto-minted on user creation; get_or_create also backfills
        # any pre-existing user so every authenticated caller always has a key.
        token, _ = Token.objects.get_or_create(user=obj)
        return token.key

    def get_github_login(self, obj) -> str | None:
        # social_django's reverse manager. Only one GitHub social_auth row
        # per user in practice; iterate so prefetch_related kicks in if a
        # caller adds it.
        for sa in obj.social_auth.all():
            if sa.provider == "github":
                return (sa.extra_data or {}).get("login") or None
        return None


class AccountUpdateSerializer(serializers.ModelSerializer):
    """Writable subset of user-tunable account preferences."""

    class Meta:
        model = User
        fields = (
            "routing_preference",
            "default_request_visibility",
            "default_collection_name",
            "public_profile_enabled",
        )

    def validate_default_collection_name(self, value):
        return value.strip()

    def validate_default_request_visibility(self, value):
        # Import here to keep accounts decoupled from inference at module load.
        from apps.inference.models import VISIBILITY_VALUES

        if value not in VISIBILITY_VALUES:
            raise serializers.ValidationError(
                f"Must be one of {sorted(VISIBILITY_VALUES)}."
            )
        return value
