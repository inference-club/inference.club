from django.apps import AppConfig


class InferenceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inference"

    def ready(self):
        # Registers the post_save receivers that give finished songs cover art.
        from . import covers  # noqa: F401
