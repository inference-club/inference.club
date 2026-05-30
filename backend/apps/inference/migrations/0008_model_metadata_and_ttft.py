from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inference", "0007_abuse_guardrails_and_tokens"),
    ]

    operations = [
        migrations.AddField(
            model_name="providermodel",
            name="metadata",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Operator-set overrides for the OpenRouter-style model "
                "catalog (e.g. name, quantization, context_length, "
                "max_output_length, input/output_modalities, supported_features, "
                "supported_sampling_parameters). Heuristics + defaults fill the rest.",
            ),
        ),
        migrations.AddField(
            model_name="inferencerequest",
            name="ttft_ms",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
