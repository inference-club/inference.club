from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inference", "0044_pinnedmodel"),
    ]

    operations = [
        migrations.AddField(
            model_name="provider",
            name="access_policy",
            field=models.CharField(
                choices=[
                    ("PRIVATE", "Only me"),
                    ("AUTHENTICATED", "Any inference.club member"),
                    ("RESTRICTED", "Specific GitHub users"),
                ],
                default="AUTHENTICATED",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="provider",
            name="allowed_github_users",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="GitHub usernames allowed when access_policy is RESTRICTED.",
            ),
        ),
    ]
