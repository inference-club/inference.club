"""Backfill ``CustomUser.handle`` from each user's GitHub login.

Sign-up has always been GitHub-only, so every existing user has a ``github``
social_auth row. Fallback (defensive): the email local-part, slugified. On
collision a numeric suffix is appended — logins are unique on GitHub so this
only fires for pathological data.
"""

import re

from django.db import migrations


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", (value or "").strip()).strip("-")
    return value.lower() or "member"


def backfill_handles(apps, schema_editor):
    User = apps.get_model("accounts", "CustomUser")
    UserSocialAuth = apps.get_model("social_django", "UserSocialAuth")

    logins = {}
    for sa in UserSocialAuth.objects.filter(provider="github"):
        extra = sa.extra_data or {}
        login = extra.get("login") if isinstance(extra, dict) else None
        if login:
            logins[sa.user_id] = login

    taken = set(
        User.objects.exclude(handle=None).values_list("handle", flat=True)
    )
    for user in User.objects.filter(handle=None):
        base = _slugify(logins.get(user.id) or user.email.split("@", 1)[0])
        candidate = base
        i = 2
        while candidate in taken:
            candidate = f"{base}-{i}"
            i += 1
        user.handle = candidate
        user.save(update_fields=["handle"])
        taken.add(candidate)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_accesspolicy_customuser_account_type_and_more"),
        ("social_django", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill_handles, migrations.RunPython.noop),
    ]
