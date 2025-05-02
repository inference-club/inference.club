from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _

from .managers import CustomUserManager


class CustomUser(AbstractUser):
    username = None
    email = models.EmailField(
        _("email address"), unique=True, validators=[validate_email]
    )

    profile_setup_complete = models.BooleanField(
        _("profile setup complete"), default=False
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
