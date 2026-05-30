"""Sync CatalogModel metadata from the HuggingFace Hub.

    python manage.py enrich_catalog          # only models not synced within the TTL
    python manage.py enrich_catalog --force  # re-sync everything
"""
from django.core.management.base import BaseCommand

from apps.inference.hf_enrich import enrich_catalog_model
from apps.inference.models import CatalogModel


class Command(BaseCommand):
    help = "Enrich CatalogModel rows (modalities, context, features) from HuggingFace."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-sync even models synced recently (ignores the TTL).",
        )

    def handle(self, *args, **opts):
        force = opts["force"]
        qs = CatalogModel.objects.exclude(hf_repo_id="")
        total = qs.count()
        synced = 0
        for c in qs:
            if enrich_catalog_model(c, force=force):
                synced += 1
                self.stdout.write(
                    f"  {c.slug}: ctx={c.native_context_length} "
                    f"in={c.input_modalities} feats={c.supported_features}"
                )
        self.stdout.write(self.style.SUCCESS(f"enriched {synced}/{total} catalog model(s)"))
