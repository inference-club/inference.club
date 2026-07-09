"""Email sign-up + confirm-before-login (PRD 20 / Epic 1).

Covers the home-lab auth path: registration creates an inactive account and
emails a link, login is blocked until confirmed, confirmation activates, and
the flag/validation/expiry guards behave.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import EmailConfirmation

User = get_user_model()

pytestmark = pytest.mark.django_db

GOOD_PW = "SuperSecret123!"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def email_on(settings):
    settings.AUTH_EMAIL_ENABLED = True
    return settings


def _register(client, email, password=GOOD_PW):
    return client.post(
        "/api/register/", {"email": email, "password": password}, format="json"
    )


def test_register_creates_inactive_user_and_emails_link(api_client, email_on, mailoutbox):
    r = _register(api_client, "New@Example.com")
    assert r.status_code == 201

    user = User.objects.get(email="new@example.com")  # normalized to lower-case
    assert user.is_active is False
    assert user.account_type == User.AccountType.EMAIL
    assert not user.is_anonymous_account  # email users are full members
    assert EmailConfirmation.objects.filter(user=user, confirmed_at__isnull=True).exists()

    assert len(mailoutbox) == 1
    assert "confirm" in mailoutbox[0].body.lower()
    assert "new@example.com" in mailoutbox[0].to


def test_login_blocked_until_confirmed_then_succeeds(api_client, email_on, mailoutbox):
    _register(api_client, "a@example.com")

    blocked = api_client.post(
        "/api/login/", {"email": "a@example.com", "password": GOOD_PW}, format="json"
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "email_unconfirmed"

    token = EmailConfirmation.objects.get(user__email="a@example.com").token
    confirmed = api_client.post("/api/auth/confirm/", {"token": token}, format="json")
    assert confirmed.status_code == 200
    assert User.objects.get(email="a@example.com").is_active is True

    ok = api_client.post(
        "/api/login/", {"email": "a@example.com", "password": GOOD_PW}, format="json"
    )
    assert ok.status_code == 200


def test_register_disabled_returns_403(api_client, settings):
    settings.AUTH_EMAIL_ENABLED = False
    r = _register(api_client, "b@example.com")
    assert r.status_code == 403
    assert not User.objects.filter(email="b@example.com").exists()


def test_confirm_invalid_token_is_400(api_client, email_on):
    r = api_client.post("/api/auth/confirm/", {"token": "not-a-real-token"}, format="json")
    assert r.status_code == 400


def test_expired_token_rejected(api_client, email_on, mailoutbox):
    _register(api_client, "c@example.com")
    conf = EmailConfirmation.objects.get(user__email="c@example.com")
    # Backdate creation beyond the TTL (default 48h).
    EmailConfirmation.objects.filter(pk=conf.pk).update(
        created_at=timezone.now() - timedelta(hours=49)
    )
    r = api_client.post("/api/auth/confirm/", {"token": conf.token}, format="json")
    assert r.status_code == 400
    assert User.objects.get(email="c@example.com").is_active is False


def test_duplicate_email_conflicts(api_client, email_on, mailoutbox):
    assert _register(api_client, "d@example.com").status_code == 201
    assert _register(api_client, "d@example.com").status_code == 409


def test_weak_password_rejected(api_client, email_on):
    r = _register(api_client, "e@example.com", password="123")
    assert r.status_code == 400
    assert not User.objects.filter(email="e@example.com").exists()


def test_resend_is_generic_and_reissues(api_client, email_on, mailoutbox):
    _register(api_client, "f@example.com")
    mailoutbox.clear()
    r = api_client.post("/api/auth/confirm/resend/", {"email": "f@example.com"}, format="json")
    assert r.status_code == 200
    assert len(mailoutbox) == 1  # a fresh link went out
    # Unknown address: same generic 200, no email.
    mailoutbox.clear()
    r2 = api_client.post(
        "/api/auth/confirm/resend/", {"email": "nobody@example.com"}, format="json"
    )
    assert r2.status_code == 200
    assert len(mailoutbox) == 0
