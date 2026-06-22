from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inference", "0036_chatthread"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatthread",
            name="source",
            field=models.CharField(
                choices=[
                    ("chat", "Chat"),
                    ("agent", "Agent"),
                    ("voice", "Voice"),
                ],
                default="chat",
                max_length=16,
            ),
        ),
    ]
