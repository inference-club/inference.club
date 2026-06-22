from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

from .managers import CustomUserManager

# Synthetic-email domain for accounts with no real identity (guests and
# passcode accounts). Never deliverable; anything that sends mail must skip it.
ANON_EMAIL_DOMAIN = "anon.inference.club"


class CustomUser(AbstractUser):
    class AccountType(models.TextChoices):
        GITHUB = "GITHUB", "GitHub"
        GUEST = "GUEST", "Guest"
        PASSCODE = "PASSCODE", "Passcode"
    # How this user's inference requests are routed when several providers
    # serve the same model. Global (not per-model) for now.
    ROUTING_ANY = "ANY"
    ROUTING_PREFER_OWN = "PREFER_OWN"
    ROUTING_ONLY_OWN = "ONLY_OWN"
    ROUTING_CHOICES = [
        (ROUTING_ANY, "Use any provider"),
        (ROUTING_PREFER_OWN, "Prefer my own nodes"),
        (ROUTING_ONLY_OWN, "Only my own nodes"),
    ]

    username = None
    email = models.EmailField(
        _("email address"), unique=True, validators=[validate_email]
    )

    # How this account authenticates and what it may do. GUEST/PASSCODE
    # ("anonymous accounts") are playground-only: no API tokens, no compute
    # registration, never-PUBLIC content. See docs/prd/08-anonymous-access.md.
    account_type = models.CharField(
        _("account type"),
        max_length=12,
        choices=AccountType.choices,
        default=AccountType.GITHUB,
        db_index=True,
    )

    # The canonical public identity: profile URL, attribution, API. For GitHub
    # users this is their GitHub login unless alias mode swaps in `anon_alias`;
    # for anonymous accounts it's always a generated three-word slug. Nullable
    # because PSA creates GitHub users before their login is known (a pipeline
    # step fills it in immediately after).
    handle = models.SlugField(
        _("handle"), max_length=80, unique=True, null=True, blank=True
    )

    # Generated once, stable across alias-mode toggles so links don't churn
    # and aliases can't be farmed by flipping the switch.
    anon_alias = models.SlugField(
        _("anonymous alias"), max_length=80, unique=True, null=True, blank=True
    )

    # GitHub users only: when on, `handle` is the alias and nothing public
    # emits the GitHub login or avatar.
    use_anon_alias = models.BooleanField(_("use anonymous alias"), default=False)

    # Alias regeneration is rate-limited (once per 30 days) to prevent
    # handle churn/squatting.
    alias_regenerated_at = models.DateTimeField(null=True, blank=True)

    # Bumped to invalidate every live session for this user (the session
    # stores the epoch at login; a middleware logs out on mismatch).
    session_epoch = models.PositiveIntegerField(default=0)

    profile_setup_complete = models.BooleanField(
        _("profile setup complete"), default=False
    )

    routing_preference = models.CharField(
        _("routing preference"),
        max_length=16,
        choices=ROUTING_CHOICES,
        default=ROUTING_ANY,
        help_text=(
            "Which providers to route this user's requests to when multiple "
            "serve the same model."
        ),
    )

    # Default visibility applied to new inference requests (see
    # docs/prd/01-content-sharing.md). Choices mirror
    # apps.inference.models.VISIBILITY_CHOICES; kept as a plain CharField here to
    # avoid an accounts→inference import. Defaults to "unlisted".
    default_request_visibility = models.CharField(
        _("default request visibility"),
        max_length=12,
        default="UNLISTED",
        help_text="Visibility applied to new inference requests unless overridden.",
    )

    # Collection (by name, the API's unique per-user handle) that new inference
    # requests are filed into unless the request names one itself. Empty means
    # "no collection". A name (not an FK) both to avoid an accounts→inference
    # import and so the preference survives the collection being deleted — the
    # next generation simply recreates it.
    default_collection_name = models.CharField(
        _("default collection name"),
        max_length=120,
        blank=True,
        default="",
        help_text="New inference requests are added to this collection "
        "(created on first use) unless the request specifies another.",
    )

    # Master switch for the user's public profile at /<github_login>. When off,
    # the public profile and its request listings are hidden from everyone.
    public_profile_enabled = models.BooleanField(
        _("public profile enabled"), default=True
    )

    # Optional personal Brave Search API key, enabling the playground Agent's
    # `web_search_brave` tool (PRD 14). Stored as-is on this single-tenant,
    # self-hosted deployment; never exposed by the API (write-only).
    brave_api_key = models.CharField(max_length=128, blank=True, default="")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    @property
    def is_anonymous_account(self) -> bool:
        """Guest or passcode account — playground-only, never holds tokens."""
        return self.account_type in (
            self.AccountType.GUEST,
            self.AccountType.PASSCODE,
        )

    def bump_session_epoch(self) -> None:
        """Invalidate every live session for this user (see middleware)."""
        type(self).objects.filter(pk=self.pk).update(
            session_epoch=models.F("session_epoch") + 1
        )
        self.refresh_from_db(fields=["session_epoch"])

    def clean(self):
        super().clean()
        # Anonymous accounts must never gain the staff surface.
        if self.is_anonymous_account and (self.is_staff or self.is_superuser):
            raise ValidationError("Anonymous accounts cannot be staff/superuser.")

    def save(self, *args, **kwargs):
        # Check if the user has a username
        if self.username:
            self.profile_setup_complete = True
        else:
            self.profile_setup_complete = False
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class AccessCode(models.Model):
    """An admin-issued passcode that *is* the login credential for one
    persistent anonymous account (created together with the code).

    Stored plaintext, deliberately: the admin must be able to re-display a
    code for a friend who lost it. These are low-privilege, individually
    revocable, hard-throttled credentials — not password-grade secrets.
    """

    code = models.CharField(max_length=40, unique=True, db_index=True)
    user = models.OneToOneField(
        "accounts.CustomUser", on_delete=models.CASCADE, related_name="access_code"
    )
    label = models.CharField(
        max_length=120, blank=True, default="", help_text='Admin note, e.g. "for Max".'
    )
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    use_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code} ({self.label or self.user.handle})"

    def is_redeemable(self) -> bool:
        from django.utils import timezone

        if not self.is_active or not self.user.is_active:
            return False
        if self.expires_at is not None and self.expires_at <= timezone.now():
            return False
        return True


class AccessPolicy(models.Model):
    """Singleton holding the real-time anonymous-access knobs the admin can
    flip without a deploy. Read on every login-page load and on anonymous
    sign-ins, so it's cached briefly (see ``load``)."""

    CACHE_KEY = "accounts:access_policy"
    CACHE_SECONDS = 30
    _SINGLETON_PK = 1

    guest_signin_enabled = models.BooleanField(default=False)
    passcode_signin_enabled = models.BooleanField(default=True)
    # Cap on non-revoked guest accounts; 0 = unlimited.
    max_active_guests = models.PositiveIntegerField(default=100)
    # Per-IP creation/attempt throttles (DRF rate strings).
    guest_creation_rate = models.CharField(max_length=20, default="5/hour")
    passcode_attempt_rate = models.CharField(max_length=20, default="10/hour")
    # Throttle rates applied to anonymous accounts on the /v1 surface.
    anon_inference_rate = models.CharField(max_length=20, default="15/min")
    anon_models_rate = models.CharField(max_length=20, default="60/min")
    # Optional banner copy shown to anonymous users (e.g. "demo weekend —
    # accounts may be reset"). Empty = no banner.
    guest_message = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "access policy"
        verbose_name_plural = "access policy"

    def __str__(self):
        return "Access policy"

    def save(self, *args, **kwargs):
        self.pk = self._SINGLETON_PK
        super().save(*args, **kwargs)
        cache.delete(self.CACHE_KEY)

    @classmethod
    def load(cls) -> "AccessPolicy":
        policy = cache.get(cls.CACHE_KEY)
        if policy is None:
            policy, _ = cls.objects.get_or_create(pk=cls._SINGLETON_PK)
            cache.set(cls.CACHE_KEY, policy, cls.CACHE_SECONDS)
        return policy


class UserApiKey(models.Model):
    """A user's personal external-service API key (Brave, ElevenLabs, …).

    Encrypted at rest (Fernet, see ``accounts.crypto``) and NEVER returned by the
    API — only a masked hint + an is-set flag. One row per (user, service); the
    service slug is validated against the registry in
    ``apps.inference.external_keys``. Shared across everything that runs as the
    user (text agent, voice agent, future tools) via ``get_user_api_key``.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_keys"
    )
    service = models.CharField(max_length=64)  # registry slug, e.g. "brave"
    label = models.CharField(max_length=120, blank=True, default="")
    value_encrypted = models.TextField(blank=True, default="")
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "service")]
        ordering = ["service"]

    def __str__(self):
        return f"UserApiKey({self.user_id}, {self.service})"

    def set_value(self, plaintext: str) -> None:
        from .crypto import encrypt_secret

        self.value_encrypted = encrypt_secret((plaintext or "").strip())

    @property
    def value(self) -> str:
        from .crypto import decrypt_secret

        return decrypt_secret(self.value_encrypted)

    @property
    def hint(self) -> str:
        """A safe-to-display preview — the last 4 chars, never the whole key."""
        v = self.value
        if not v:
            return ""
        return f"…{v[-4:]}" if len(v) >= 8 else "set"
