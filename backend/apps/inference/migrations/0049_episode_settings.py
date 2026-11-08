from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inference", "0048_provider_agent_control_token_serviceaction"),
    ]

    operations = [
        migrations.AddField(
            model_name="episode",
            name="settings",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
