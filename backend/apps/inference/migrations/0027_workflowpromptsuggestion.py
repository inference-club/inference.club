from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inference", "0026_inferencerequest_attempts_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkflowPromptSuggestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("template_key", models.CharField(db_index=True, max_length=64)),
                ("text", models.TextField()),
                ("created_on", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["id"],
            },
        ),
    ]
