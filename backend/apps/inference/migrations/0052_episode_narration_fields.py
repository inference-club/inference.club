import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inference", "0051_collection_share_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="episode",
            name="source",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="episode",
            name="production",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="episode",
            name="audio",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to="inference.mediaasset",
            ),
        ),
        migrations.AddField(
            model_name="episode",
            name="cover_request",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to="inference.inferencerequest",
            ),
        ),
    ]
