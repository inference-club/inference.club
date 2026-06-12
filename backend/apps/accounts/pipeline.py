"""Custom python-social-auth pipeline steps (appended after the defaults).

Two jobs:

1. ``finalize_anonymous_upgrade`` — the "Keep this account" flow. PSA's
   default pipeline already associates the GitHub identity with the
   *currently logged-in* user (``social_user`` + ``associate_user``), so when
   a guest/passcode user goes through OAuth, all that's left is flipping the
   account to a full member. If the GitHub identity is already bound to a
   different user, ``social_user`` raises AuthAlreadyAssociated before we run.

2. ``set_handle_from_github`` — keeps ``CustomUser.handle`` in sync with the
   GitHub login for non-aliased GitHub users (covers brand-new signups, the
   pre-handle backfill, and GitHub renames). Aliased users keep their alias.
"""

import logging

from rest_framework.authtoken.models import Token

from .handles import dedupe_handle
from .models import ANON_EMAIL_DOMAIN, CustomUser

logger = logging.getLogger("django")


def _github_login(details, response) -> str | None:
    if isinstance(response, dict) and response.get("login"):
        return response["login"]
    return (details or {}).get("username") or None


def finalize_anonymous_upgrade(
    strategy, details, backend, user=None, response=None, *args, **kwargs
):
    """Upgrade a guest/passcode account that just linked a GitHub identity."""
    if user is None or not user.is_anonymous_account:
        return None

    update_fields = ["account_type", "use_anon_alias"]
    user.account_type = CustomUser.AccountType.GITHUB
    # Upgrading must not deanonymize: keep going by the generated handle.
    # The user can switch to their GitHub handle in settings afterwards.
    user.use_anon_alias = True
    if not user.anon_alias and user.handle:
        user.anon_alias = user.handle
        update_fields.append("anon_alias")

    # Swap the synthetic @anon. email for the real one when it's free. A
    # collision here is near-impossible (the identity itself would have been
    # associated with that account), so keeping the synthetic email is a safe
    # fallback rather than aborting the upgrade.
    real_email = (details or {}).get("email") or ""
    if (
        real_email
        and user.email.endswith("@" + ANON_EMAIL_DOMAIN)
        and not CustomUser.objects.filter(email__iexact=real_email)
        .exclude(pk=user.pk)
        .exists()
    ):
        user.email = real_email
        update_fields.append("email")

    user.save(update_fields=update_fields)

    # Full members hold an API token; mint the one the signal skipped.
    Token.objects.get_or_create(user=user)

    # A passcode must not remain a backdoor into a now-real account.
    code = getattr(user, "access_code", None)
    if code is not None and code.is_active:
        code.is_active = False
        code.save(update_fields=["is_active"])

    logger.info("anonymous account %s upgraded to GitHub account", user.handle)
    return None


def set_handle_from_github(
    strategy, details, backend, user=None, response=None, *args, **kwargs
):
    """Adopt/sync the GitHub login as the handle for non-aliased users."""
    if user is None or backend.name != "github":
        return None
    if user.account_type != CustomUser.AccountType.GITHUB or user.use_anon_alias:
        return None
    login = _github_login(details, response)
    if not login:
        return None
    login = login.lower()
    if user.handle and user.handle.lower() == login:
        return None
    user.handle = dedupe_handle(login, exclude_pk=user.pk)
    user.save(update_fields=["handle"])
    return None
