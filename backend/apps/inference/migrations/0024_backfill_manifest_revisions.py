# Seed story-mode history (PRD 07 V3) with each provider's current manifest,
# so the timeline starts at "now" instead of empty. Only valid manifests —
# history records what the cluster looked like, not operator typos. The
# revision keeps the manifest's uploaded_at (auto_now_add is bypassed with a
# queryset update) so the first scrubber tick lands on a truthful date.

from django.db import migrations


def backfill(apps, schema_editor):
    ServiceManifest = apps.get_model("inference", "ServiceManifest")
    ManifestRevision = apps.get_model("inference", "ManifestRevision")
    for manifest in ServiceManifest.objects.filter(is_valid=True).select_related(
        "provider"
    ):
        rev = ManifestRevision.objects.create(
            provider=manifest.provider,
            schema_version=manifest.schema_version,
            parsed=manifest.parsed,
        )
        ManifestRevision.objects.filter(id=rev.id).update(
            uploaded_at=manifest.uploaded_at
        )


def unbackfill(apps, schema_editor):
    apps.get_model("inference", "ManifestRevision").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("inference", "0023_manifestrevision"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
