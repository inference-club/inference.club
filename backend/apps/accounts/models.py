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
