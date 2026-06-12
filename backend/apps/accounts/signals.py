"""Account-related signal handlers."""

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.authtoken.models import Token

from .middleware import SESSION_EPOCH_KEY


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_api_token(sender, instance, created, **kwargs):
    """Auto-mint a DRF API token the moment a user is created.

    New users sign in with GitHub and land in the dashboard already holding a
    key, so the "make your first request" path has no separate token-minting
    detour. Idempotent: existing users are backfilled lazily by the serializer.

    Guest/passcode accounts are playground-only and must never hold a Bearer
    key — skipped here and everywhere tokens are minted.
    """
    if created and not instance.is_anonymous_account:
        Token.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def stamp_session_epoch(sender, request, user, **kwargs):
    """Record the user's current session epoch in the fresh session, so a
    later ``bump_session_epoch()`` invalidates it (see middleware)."""
    if request is not None:
        request.session[SESSION_EPOCH_KEY] = getattr(user, "session_epoch", 0)
