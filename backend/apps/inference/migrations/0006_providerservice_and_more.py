import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inference", "0005_servicemanifest"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProviderService",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                ("modified_on", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255)),
                (
                    "host_id",
                    models.CharField(
                        blank=True,
                        help_text="Manifest host id, for display.",
                        max_length=255,
                    ),
                ),
                ("engine", models.CharField(blank=True, max_length=64)),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="False when the service is no longer present in the latest manifest.",
                    ),
                ),
                (
                    "access_policy",
                    models.CharField(
                        choices=[
                            ("PRIVATE", "Only me"),
                            ("AUTHENTICATED", "Any inference.club member"),
                            ("RESTRICTED", "Specific GitHub users"),
                        ],
                        default="PRIVATE",
                        max_length=16,
                    ),
                ),
                (
                    "allowed_github_users",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="GitHub usernames allowed when access_policy is RESTRICTED.",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_created_by",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_modified_by",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="services",
                        to="inference.provider",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="providermodel",
            name="service",
            field=models.ForeignKey(
                blank=True,
                help_text="The service that serves this model, when known from the "
                "manifest. Models discovered only via live /v1/models stay unlinked "
                "and remain owner-only.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="models",
                to="inference.providerservice",
            ),
        ),
        migrations.AddConstraint(
            model_name="providerservice",
            constraint=models.UniqueConstraint(
                fields=("provider", "name"), name="unique_service_name_per_provider"
            ),
        ),
    ]
