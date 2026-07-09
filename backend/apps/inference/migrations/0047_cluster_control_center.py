from django.db import migrations, models


class Migration(migrations.Migration):
    """Cluster control center (PRD 21) — V0 data model.

    Owner opt-in on the provider, plus the two per-service fields the fit
    preflight and the "where can it run" affordance need. All additive and
    nullable/defaulted, so existing rows and manifest re-uploads are unaffected.
    """

    dependencies = [
        ("inference", "0046_host_access_policy"),
    ]

    operations = [
        migrations.AddField(
            model_name="provider",
            name="cluster_control_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Owner opt-in: expose this cluster in the control "
                "center for park/unpark of inference services (PRD 21).",
            ),
        ),
        migrations.AddField(
            model_name="providerservice",
            name="expected_vram_gb",
            field=models.FloatField(
                blank=True,
                null=True,
                help_text="Expected GPU memory (GiB) when running; drives the "
                "fit preflight while parked. Auto-learned from observed peak "
                "(PRD 21).",
            ),
        ),
        migrations.AddField(
            model_name="providerservice",
            name="candidate_boxes",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Manifest box ids this service can run on (arch + "
                "weight availability). Empty = home box only (PRD 21).",
            ),
        ),
    ]
