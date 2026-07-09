"""Transactional email for the email sign-up flow (PRD 20 / Epic 1).

Only used where AUTH_EMAIL_ENABLED. Synthetic guest/passcode addresses are
never deliverable, so anything here skips them defensively.
"""

from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import send_mail

from .models import ANON_EMAIL_DOMAIN


def confirmation_link(token: str) -> str:
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/confirm?{urlencode({'token': token})}"


def send_confirmation_email(user, confirmation) -> None:
    """Email the account-confirmation link. No-op for synthetic addresses."""
    if user.email.endswith(f"@{ANON_EMAIL_DOMAIN}"):
        return

    link = confirmation_link(confirmation.token)
    ttl = settings.EMAIL_CONFIRMATION_TTL_HOURS
    subject = "Confirm your inference.club account"
    body = (
        "Welcome to inference.club!\n\n"
        "Confirm your account by opening this link:\n\n"
        f"{link}\n\n"
        f"The link expires in {ttl} hours. "
        "If you didn't create an account, you can safely ignore this email.\n"
    )
    send_mail(
        subject,
        body,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )
