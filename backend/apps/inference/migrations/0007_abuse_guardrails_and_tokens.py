from django.db import migrations, models


def backfill_tokens(apps, schema_editor):
    """Populate the new token columns from each request's stored
    ``results.usage`` so the leaderboard has data from day one."""
    InferenceRequest = apps.get_model("inference", "InferenceRequest")
    for ir in InferenceRequest.objects.exclude(results__isnull=True).iterator():
        results = ir.results
        if not isinstance(results, dict):
            continue
        usage = results.get("usage")
        if not isinstance(usage, dict):
            continue

        def _as_int(v):
            return v if isinstance(v, int) and v >= 0 else None

        prompt = _as_int(usage.get("prompt_tokens"))
        completion = _as_int(usage.get("completion_tokens"))
        total = _as_int(usage.get("total_tokens"))
        if total is None and (prompt is not None or completion is not None):
            total = (prompt or 0) + (completion or 0)
        if prompt is None and completion is None and total is None:
            continue
        ir.prompt_tokens = prompt
        ir.completion_tokens = completion
        ir.total_tokens = total
        ir.save(update_fields=["prompt_tokens", "completion_tokens", "total_tokens"])


class Migration(migrations.Migration):

    dependencies = [
        ("inference", "0006_providerservice_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="provider",
            name="accepting_requests",
            field=models.BooleanField(
                default=True,
                help_text="Kill switch — when False the node is excluded from "
                "routing for everyone (including the owner), so it serves no "
                "inference.",
            ),
        ),
        migrations.AddField(
            model_name="inferencerequest",
            name="prompt_tokens",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="inferencerequest",
            name="completion_tokens",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="inferencerequest",
            name="total_tokens",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="inferencerequest",
            index=models.Index(fields=["created_on"], name="ir_created_on_idx"),
        ),
        migrations.RunPython(backfill_tokens, migrations.RunPython.noop),
    ]
