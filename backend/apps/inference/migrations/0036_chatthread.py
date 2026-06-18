import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("inference", "0035_inferencerequest_public_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatThread",
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
                ("created_on", models.DateTimeField(auto_now_add=True, editable=False)),
                ("modified_on", models.DateTimeField(auto_now=True, editable=False)),
                ("title", models.CharField(blank=True, default="", max_length=200)),
                ("model", models.CharField(blank=True, default="", max_length=255)),
                ("messages", models.JSONField(blank=True, default=list)),
                ("message_count", models.PositiveIntegerField(default=0)),
                ("prompt_tokens", models.PositiveIntegerField(default=0)),
                ("completion_tokens", models.PositiveIntegerField(default=0)),
                ("total_tokens", models.PositiveIntegerField(default=0)),
                ("has_logprobs", models.BooleanField(default=False)),
                ("title_generated", models.BooleanField(default=False)),
                (
                    "public_id",
                    models.CharField(
                        blank=True,
                        editable=False,
                        max_length=24,
                        null=True,
                        unique=True,
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
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_threads",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-modified_on"],
            },
        ),
        migrations.AddIndex(
            model_name="chatthread",
            index=models.Index(
                fields=["user", "modified_on"], name="chatthread_user_mod_idx"
            ),
        ),
    ]
