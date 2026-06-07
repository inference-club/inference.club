from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """Grant (or revoke) staff/superuser status for a user, by email.

    Signup is GitHub-only, so there's no createsuperuser flow for real members.
    This command promotes an existing account to staff so it can reach the
    in-app admin surface (and optionally the Django admin via --superuser).

    Examples:
        python manage.py make_staff briancaffey2010@gmail.com
        python manage.py make_staff briancaffey2010@gmail.com --superuser
        python manage.py make_staff someone@example.com --revoke
    """

    help = "Grant or revoke staff/superuser status for a user by email."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Email of the user to modify.")
        parser.add_argument(
            "--superuser",
            action="store_true",
            help="Also grant (or, with --revoke, remove) superuser status.",
        )
        parser.add_argument(
            "--revoke",
            action="store_true",
            help="Revoke instead of grant.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        email = options["email"].strip()
        grant = not options["revoke"]
        touch_super = options["superuser"]

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise CommandError(f"No user with email {email!r}.")

        user.is_staff = grant
        if touch_super:
            user.is_superuser = grant
        fields = ["is_staff"] + (["is_superuser"] if touch_super else [])
        user.save(update_fields=fields)

        verb = "Granted" if grant else "Revoked"
        roles = "staff" + ("+superuser" if touch_super else "")
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {roles} for {user.email} "
                f"(is_staff={user.is_staff}, is_superuser={user.is_superuser})."
            )
        )
