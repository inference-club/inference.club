from django.conf import settings
from django.db import models
from apps.core.models import BaseModel


class InferenceRequest(BaseModel):
    INFERENCE_TYPES = (
        ("LLM", "Language Model"),
        ("IMAGE", "Image Generation"),
        ("VIDEO", "Video Generation"),
        ("TTS", "Text to Speech"),
    )

    STATUS_CHOICES = (
        ("REQUESTED", "Requested"),
        ("QUEUED", "Queued"),
        ("PROCESSING", "Processing"),
        ("PROCESSED", "Processed"),
        ("SAVED", "Saved"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="inference_requests",
    )
    inference_type = models.CharField(max_length=32, choices=INFERENCE_TYPES)
    payload = models.JSONField()
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default="REQUESTED"
    )
    results = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created_on"]
        indexes = [
            models.Index(fields=["user", "status", "created_on"]),
        ]

    def __str__(self):
        return f"{self.inference_type} request by {self.user.username} ({self.status})"
