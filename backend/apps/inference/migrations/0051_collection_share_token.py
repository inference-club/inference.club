from django.db import migrations, models

from apps.inference.models import generate_share_token


def fill_tokens(apps, schema_editor):
    Collection = apps.get_model("inference", "Collection")
    for col in Collection.objects.filter(share_token__isnull=True).iterator():
        col.share_token = generate_share_token()
        col.save(update_fields=["share_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("inference", "0050_request_title"),
    ]

    operations = [
        migrations.AddField(
            model_name="collection",
            name="share_token",
            field=models.CharField(
                blank=True, editable=False, max_length=32, null=True, unique=True
            ),
        ),
        migrations.RunPython(fill_tokens, migrations.RunPython.noop),
    ]
