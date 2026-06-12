"""Purge anonymous (guest/passcode) accounts and their content.

Guests are persistent-by-decision (PRD 08), so nothing runs automatically —
this is the manual/cron cleanup lever:

    manage.py purge_anonymous --revoked-only --dry-run
    manage.py purge_anonymous --inactive-days 90 --include-passcodes
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Delete guest (and optionally passcode) accounts plus their content."

    def add_arguments(self, parser):
        parser.add_argument(
            "--inactive-days",
            type=int,
            default=None,
            help="Only accounts with no login and no requests in the last N days.",
        )
        parser.add_argument(
            "--revoked-only",
            action="store_true",
            help="Only accounts already locked (is_active=False).",
        )
        parser.add_argument(
            "--include-passcodes",
            action="store_true",
            help="Also purge PASSCODE accounts (default: guests only).",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Report, delete nothing."
        )

    def handle(self, *args, **opts):
        User = get_user_model()
        types = [User.AccountType.GUEST]
        if opts["include_passcodes"]:
            types.append(User.AccountType.PASSCODE)
        qs = User.objects.filter(account_type__in=types)

        if opts["revoked_only"]:
            qs = qs.filter(is_active=False)
        if opts["inactive_days"] is not None:
            cutoff = timezone.now() - timedelta(days=opts["inactive_days"])
            qs = qs.exclude(last_login__gte=cutoff).exclude(
                inference_requests__created_on__gte=cutoff
            )

        qs = qs.distinct()
        total = qs.count()
        if total == 0:
            self.stdout.write("Nothing to purge.")
            return

        for user in qs:
            n_requests = user.inference_requests.count()
            self.stdout.write(
                f"{'DRY-RUN ' if opts['dry_run'] else ''}purge "
                f"{user.handle} ({user.account_type}, {n_requests} requests, "
                f"last_login={user.last_login})"
            )
            if not opts["dry_run"]:
                # Request FK is SET_NULL — delete content explicitly so the
                # purge doesn't leave ownerless rows behind.
                user.inference_requests.all().delete()
                user.delete()

        verb = "Would purge" if opts["dry_run"] else "Purged"
        self.stdout.write(self.style.SUCCESS(f"{verb} {total} account(s)."))
