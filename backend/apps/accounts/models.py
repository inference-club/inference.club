from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _

from .managers import CustomUserManager


class CustomUser(AbstractUser):
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

    # Master switch for the user's public profile at /<github_login>. When off,
    # the public profile and its request listings are hidden from everyone.
    public_profile_enabled = models.BooleanField(
        _("public profile enabled"), default=True
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def save(self, *args, **kwargs):
        # Check if the user has a username
        if self.username:
            self.profile_setup_complete = True
        else:
            self.profile_setup_complete = False
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
