"""Account-creation and alias services for anonymous access (PRD 08)."""

from django.db import transaction
from django.utils import timezone

from .handles import dedupe_handle, generate_access_code, generate_unique_handle
from .models import ANON_EMAIL_DOMAIN, AccessCode, CustomUser

ALIAS_REGENERATE_COOLDOWN_DAYS = 30


def create_anonymous_user(account_type: str) -> CustomUser:
    """A new guest/passcode user: generated handle (which is also its alias),
    synthetic email, unusable password, UNLISTED default visibility."""
    handle = generate_unique_handle()
    return CustomUser.objects.create_user(
        email=f"{handle}@{ANON_EMAIL_DOMAIN}",
        account_type=account_type,
        handle=handle,
        anon_alias=handle,
        default_request_visibility="UNLISTED",
    )


@transaction.atomic
def create_access_code(created_by, label: str = "", expires_at=None) -> AccessCode:
    """Mint a passcode together with the persistent account it logs into."""
    user = create_anonymous_user(CustomUser.AccountType.PASSCODE)
    return AccessCode.objects.create(
        code=generate_access_code(),
        user=user,
        label=label or "",
        expires_at=expires_at,
        created_by=created_by,
    )


def revoke_anonymous_user(user: CustomUser, deactivate: bool = True) -> None:
    """Kill all live sessions; optionally lock the account entirely."""
    user.bump_session_epoch()
    if deactivate and user.is_active:
        user.is_active = False
        user.save(update_fields=["is_active"])


def set_alias_mode(user: CustomUser, enabled: bool) -> CustomUser:
    """Toggle a GitHub user's anonymous alias (full handle swap).

    Off→on generates the alias once and reuses it forever after. On→off
    restores the GitHub login as the handle. Anonymous accounts are always
    aliased — callers must not let them reach this.
    """
    if enabled == user.use_anon_alias:
        return user
    update = ["use_anon_alias", "handle"]
    if enabled:
        if not user.anon_alias:
            user.anon_alias = generate_unique_handle()
            update.append("anon_alias")
        user.use_anon_alias = True
        user.handle = user.anon_alias
    else:
        login = _github_login_of(user)
        if not login:
            raise ValueError("no GitHub login to restore as the handle")
        user.use_anon_alias = False
        user.handle = dedupe_handle(login.lower(), exclude_pk=user.pk)
    user.save(update_fields=update)
    return user


def regenerate_alias(user: CustomUser) -> CustomUser:
    """A fresh alias, at most once per cooldown window. Returns the user;
    raises ValueError when still cooling down."""
    now = timezone.now()
    if user.alias_regenerated_at is not None:
        elapsed = now - user.alias_regenerated_at
        if elapsed.days < ALIAS_REGENERATE_COOLDOWN_DAYS:
            raise ValueError(
                f"Alias can be regenerated once every "
                f"{ALIAS_REGENERATE_COOLDOWN_DAYS} days."
            )
    user.anon_alias = generate_unique_handle()
    user.alias_regenerated_at = now
    update = ["anon_alias", "alias_regenerated_at"]
    if user.use_anon_alias or user.is_anonymous_account:
        user.handle = user.anon_alias
        update.append("handle")
    user.save(update_fields=update)
    return user


def _github_login_of(user) -> str | None:
    for sa in user.social_auth.all():
        if sa.provider == "github":
            return (sa.extra_data or {}).get("login") or None
    return None
