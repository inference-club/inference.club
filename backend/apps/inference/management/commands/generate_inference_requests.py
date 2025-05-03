from django.core.management.base import BaseCommand
from apps.inference.factories import InferenceRequestFactory
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Generates random inference requests for testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=10,
            help="Number of inference requests to generate",
        )
        parser.add_argument(
            "--user",
            type=str,
            help="Email of the user to create requests for (optional)",
        )

    def handle(self, *args, **options):
        count = options["count"]
        user_email = options["user"]

        if user_email:
            try:
                user = User.objects.get(email=user_email)
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"User with email {user_email} does not exist")
                )
                return
        else:
            # Get or create a test user if none specified
            user, _ = User.objects.get_or_create(
                email="test@example.com",
                defaults={
                    "username": "testuser",
                    "is_active": True,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Generating {count} inference requests for user {user.email}"
            )
        )

        # Generate the requests
        requests = InferenceRequestFactory.create_batch(count, user=user)

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created {len(requests)} inference requests"
            )
        )
