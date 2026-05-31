"""Account-related signal handlers."""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.authtoken.models import Token


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_api_token(sender, instance, created, **kwargs):
    """Auto-mint a DRF API token the moment a user is created.

    New users sign in with GitHub and land in the dashboard already holding a
    key, so the "make your first request" path has no separate token-minting
    detour. Idempotent: existing users are backfilled lazily by the serializer.
    """
    if created:
        Token.objects.get_or_create(user=instance)
