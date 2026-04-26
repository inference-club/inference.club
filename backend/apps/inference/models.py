from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel

# A provider is considered online if its last heartbeat is within this window.
# The agent posts every 30s; 60s gives one missed beat of grace.
PROVIDER_HEARTBEAT_TIMEOUT = timedelta(seconds=60)


class Provider(BaseModel):
    """A user-owned agent that proxies inference to local hardware."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="providers",
    )
    name = models.CharField(max_length=128)
    callback_url = models.URLField(
        help_text="Reachable URL of the agent, e.g. http://192.168.5.173:8002/v1",
    )
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"], name="unique_provider_name_per_user"
            )
        ]

    def __str__(self):
        return f"{self.user_id}:{self.name}"

    @property
    def is_online(self) -> bool:
        if not self.is_active or self.last_heartbeat_at is None:
            return False
        return timezone.now() - self.last_heartbeat_at <= PROVIDER_HEARTBEAT_TIMEOUT


class ProviderModel(BaseModel):
    """An LLM model an agent reports it can serve."""

    provider = models.ForeignKey(
        Provider, on_delete=models.CASCADE, related_name="models"
    )
    name = models.CharField(max_length=255)
    context_window = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "name"], name="unique_model_name_per_provider"
            )
        ]

    def __str__(self):
        return f"{self.provider}/{self.name}"


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
    provider = models.ForeignKey(
        Provider,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inference_requests",
    )
    model_name = models.CharField(max_length=255, blank=True, default="")
    inference_type = models.CharField(max_length=32, choices=INFERENCE_TYPES)
    payload = models.JSONField()
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default="REQUESTED"
    )
    results = models.JSONField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_on"]
        indexes = [
            models.Index(fields=["user", "status", "created_on"]),
        ]

    def __str__(self):
        return f"{self.inference_type} request by {self.user.username} ({self.status})"
