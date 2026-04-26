from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel

# How long after the last successful proxy / probe a provider stays "online"
# without any new evidence. Two minutes leaves room for occasional latency
# spikes without flapping the UI.
PROVIDER_LAST_SEEN_WINDOW = timedelta(seconds=120)


class Provider(BaseModel):
    """A user-owned agent reachable over the inference.club Tailscale network.

    The agent registers once via POST /api/inference/agent/register/, gets a
    Tailscale auth key, and joins the tailnet. The server reaches it by its
    tailnet hostname (e.g. ``club-host-17``) on ``agent_port``.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="providers",
    )
    name = models.CharField(max_length=128)
    tailnet_hostname = models.CharField(
        max_length=255,
        blank=True,
        help_text="Tailscale MagicDNS hostname inside the inference.club tailnet "
        "(e.g. 'club-host-17'). Empty until the agent has registered.",
    )
    agent_port = models.PositiveIntegerField(default=443)
    registered_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Bumped on every successful proxied request and every "
        "successful liveness probe.",
    )
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

    def _fqdn(self) -> str:
        """Resolve the tailnet hostname to a full FQDN if possible.

        We need the FQDN to match the cert Tailscale issues for the agent's
        ``*.ts.net`` device name. If TAILSCALE_TAILNET isn't configured, fall
        back to the bare hostname (callers must use verify=False in that case).
        """
        host = self.tailnet_hostname
        if not host or "." in host:
            return host
        tailnet = getattr(settings, "TAILSCALE_TAILNET", "") or ""
        if tailnet and tailnet != "-":
            tailnet = tailnet.removesuffix(".ts.net")
            return f"{host}.{tailnet}.ts.net"
        return host

    @property
    def tailnet_base_url(self) -> str:
        host = self._fqdn()
        if not host:
            return ""
        # Plain HTTP regardless of port. The agent uses tsnet's Listen()
        # (not ListenTLS), so it serves HTTP even on :443. The wire is
        # already encrypted by Tailscale's WireGuard tunnel.
        return f"http://{host}:{self.agent_port}/v1"

    @property
    def healthz_url(self) -> str:
        host = self._fqdn()
        if not host:
            return ""
        return f"http://{host}:{self.agent_port}/healthz"

    @property
    def is_online(self) -> bool:
        if not self.is_active or not self.tailnet_hostname:
            return False
        if self.last_seen_at is None:
            return False
        return timezone.now() - self.last_seen_at <= PROVIDER_LAST_SEEN_WINDOW


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
