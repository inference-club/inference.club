import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_customuser_brave_api_key"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserApiKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("service", models.CharField(max_length=64)),
                ("label", models.CharField(blank=True, default="", max_length=120)),
                ("value_encrypted", models.TextField(blank=True, default="")),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                ("modified_on", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="api_keys",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["service"],
                "unique_together": {("user", "service")},
            },
        ),
    ]
