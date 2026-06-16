import secrets

from django.db import migrations, models


def backfill_public_ids(apps, schema_editor):
    """Give every existing request an opaque public_id (new rows get one in
    Model.save). token_urlsafe(8) collisions are astronomically unlikely, but
    loop just in case."""
    InferenceRequest = apps.get_model("inference", "InferenceRequest")
    used = set(
        InferenceRequest.objects.exclude(public_id__isnull=True).values_list(
            "public_id", flat=True
        )
    )
    for pk in InferenceRequest.objects.filter(public_id__isnull=True).values_list(
        "id", flat=True
    ):
        token = secrets.token_urlsafe(8)
        while token in used:
            token = secrets.token_urlsafe(8)
        used.add(token)
        InferenceRequest.objects.filter(pk=pk).update(public_id=token)


class Migration(migrations.Migration):

    dependencies = [
        ("inference", "0034_segment_status_queued"),
    ]

    operations = [
        migrations.AddField(
            model_name="inferencerequest",
            name="public_id",
            field=models.CharField(
                blank=True, editable=False, max_length=24, null=True, unique=True
            ),
        ),
        migrations.RunPython(backfill_public_ids, migrations.RunPython.noop),
    ]
