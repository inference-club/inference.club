import re

from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifier
    for authentication instead of usernames.
    """

    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a User with the given email and password.
        Password is optional so social-auth can create users without one.

        Every user gets a ``handle`` (the canonical public identity, PRD 08).
        When the caller doesn't supply one, it's derived from the email
        local-part; GitHub sign-ins then overwrite it with the GitHub login
        in the social-auth pipeline.
        """
        if not email:
            raise ValueError(_("The Email must be set"))
        email = self.normalize_email(email)
        if not extra_fields.get("handle"):
            from .handles import dedupe_handle

            local = re.sub(r"[^a-zA-Z0-9_-]+", "-", email.split("@", 1)[0])
            extra_fields["handle"] = dedupe_handle(
                local.strip("-").lower() or "member"
            )
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:  # pragma: no cover
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))
        return self.create_user(email, password, **extra_fields)
