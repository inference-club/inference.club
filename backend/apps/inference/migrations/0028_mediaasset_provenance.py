from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inference", "0027_workflowpromptsuggestion"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mediaasset",
            name="kind",
            field=models.CharField(
                choices=[
                    ("INPUT_AUDIO", "Input audio"),
                    ("OUTPUT_AUDIO", "Output audio"),
                    ("INPUT_IMAGE", "Input image"),
                    ("OUTPUT_IMAGE", "Output image"),
                    ("OUTPUT_MODEL", "Output 3D model"),
                    ("OUTPUT_VIDEO", "Output video"),
                    ("INPUT_DOC", "Input document"),
                    ("OUTPUT_DOC", "Output document"),
                    ("OUTPUT_SUBTITLE", "Output subtitle"),
                ],
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="mediaasset",
            name="derived_from",
            field=models.ManyToManyField(
                blank=True, related_name="derivatives", to="inference.mediaasset"
            ),
        ),
    ]
