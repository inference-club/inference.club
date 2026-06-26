import secrets

from django.db import migrations, models


def backfill_public_ids(apps, schema_editor):
    """Give every existing media asset an opaque public_id (new rows get one in
    MediaAsset.save). token_urlsafe(8) collisions are astronomically unlikely,
    but loop just in case. See docs/prd/17-user-uploaded-media.md §4.2.

    visibility needs no backfill: it defaults to SECRET (owner-only), and every
    asset bound to an inference request follows that request's visibility at
    read time (``MediaAsset.is_visible_to``), so an output image of a PUBLIC
    request stays public regardless of this column. Only standalone assets
    consult their own visibility — and owner-only is the correct, safe default.
    """
    MediaAsset = apps.get_model("inference", "MediaAsset")
    used = set(
        MediaAsset.objects.exclude(public_id__isnull=True).values_list(
            "public_id", flat=True
        )
    )
    for pk in MediaAsset.objects.filter(public_id__isnull=True).values_list(
        "id", flat=True
    ):
        token = secrets.token_urlsafe(8)
        while token in used:
            token = secrets.token_urlsafe(8)
        used.add(token)
        MediaAsset.objects.filter(pk=pk).update(public_id=token)


class Migration(migrations.Migration):

    dependencies = [
        ("inference", "0041_alter_provider_tailnet_hostname"),
    ]

    operations = [
        migrations.AddField(
            model_name="mediaasset",
            name="public_id",
            field=models.CharField(
                blank=True, max_length=64, null=True, unique=True
            ),
        ),
        migrations.AddField(
            model_name="mediaasset",
            name="visibility",
            field=models.CharField(
                choices=[
                    ("PUBLIC", "Public"),
                    ("UNLISTED", "Unlisted"),
                    ("PRIVATE", "Members only"),
                    ("SECRET", "Only me"),
                ],
                db_index=True,
                default="SECRET",
                max_length=12,
            ),
        ),
        migrations.RunPython(backfill_public_ids, migrations.RunPython.noop),
    ]
