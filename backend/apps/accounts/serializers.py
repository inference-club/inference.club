from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.authtoken.models import Token

from .services import set_alias_mode

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):

    github_login = serializers.SerializerMethodField()
    api_token = serializers.SerializerMethodField()
    is_anonymous_account = serializers.SerializerMethodField()

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
            "handle",
            "account_type",
            "is_anonymous_account",
            "anon_alias",
            "use_anon_alias",
            "alias_regenerated_at",
            "routing_preference",
            "fallback_model",
            "default_request_visibility",
            "default_collection_name",
            "public_profile_enabled",
        )

    def get_api_token(self, obj) -> str | None:
        # Tokens are auto-minted on user creation; get_or_create also backfills
        # any pre-existing user so every authenticated caller always has a key.
        # Guest/passcode accounts are playground-only and never hold one.
        if obj.is_anonymous_account:
            return None
        token, _ = Token.objects.get_or_create(user=obj)
        return token.key

    def get_github_login(self, obj) -> str | None:
        # The caller's own GitHub login (this serializer feeds /api/account/,
        # i.e. the owner's private view — alias mode hides it publicly, not
        # from the user themselves). social_django's reverse manager; iterate
        # so prefetch_related kicks in if a caller adds it.
        for sa in obj.social_auth.all():
            if sa.provider == "github":
                return (sa.extra_data or {}).get("login") or None
        return None

    def get_is_anonymous_account(self, obj) -> bool:
        return obj.is_anonymous_account


class AccountUpdateSerializer(serializers.ModelSerializer):
    """Writable subset of user-tunable account preferences."""

    use_anon_alias = serializers.BooleanField(required=False)

    class Meta:
        model = User
        fields = (
            "routing_preference",
            "fallback_model",
            "default_request_visibility",
            "default_collection_name",
            "public_profile_enabled",
            "use_anon_alias",
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
        if value == "PUBLIC" and self.instance and self.instance.is_anonymous_account:
            raise serializers.ValidationError(
                "Guest and passcode accounts cannot publish publicly."
            )
        return value

    def validate_use_anon_alias(self, value):
        if self.instance and self.instance.is_anonymous_account:
            raise serializers.ValidationError(
                "Guest and passcode accounts always use their generated handle."
            )
        return value

    def update(self, instance, validated_data):
        # The alias toggle swaps `handle` too, so it goes through the service.
        alias = validated_data.pop("use_anon_alias", None)
        instance = super().update(instance, validated_data)
        if alias is not None and alias != instance.use_anon_alias:
            try:
                instance = set_alias_mode(instance, alias)
            except ValueError as exc:
                raise serializers.ValidationError({"use_anon_alias": str(exc)})
        return instance
