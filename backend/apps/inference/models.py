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
    accepting_requests = models.BooleanField(
        default=True,
        help_text="Kill switch — when False the node is excluded from routing "
        "for everyone (including the owner), so it serves no inference.",
    )
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

    @property
    def tailnet_base_url(self) -> str:
        """Plain HTTP via the *short* MagicDNS name.

        Tailscale's userspace SOCKS5 resolves short MagicDNS names within the
        tailnet but doesn't reliably resolve FQDNs like
        ``host.<tailnet>.ts.net``. We don't need the FQDN since there's no
        TLS to validate (the agent serves HTTP and the WireGuard tunnel
        already encrypts the wire).
        """
        host = self.tailnet_hostname
        if not host:
            return ""
        return f"http://{host}:{self.agent_port}/v1"

    @property
    def healthz_url(self) -> str:
        host = self.tailnet_hostname
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


class ProviderService(BaseModel):
    """One OpenAI-compatible service exposed by a provider's agent (e.g. a
    vLLM or LM Studio instance), mirrored from the uploaded manifest's
    ``hosts[].services[]``. Services are the unit of access control: an
    operator decides, per service, who in inference.club may route to it.

    Keyed by ``(provider, name)`` — the manifest guarantees service ``name``
    is unique within an agent. Re-uploading a manifest upserts by name and
    *preserves* the operator's access settings.
    """

    # Who may route inference requests to this service.
    ACCESS_PRIVATE = "PRIVATE"  # only the owner (default; preserves prior behavior)
    ACCESS_AUTHENTICATED = "AUTHENTICATED"  # any signed-in inference.club member
    ACCESS_RESTRICTED = "RESTRICTED"  # an explicit GitHub-username allowlist
    ACCESS_POLICY_CHOICES = (
        (ACCESS_PRIVATE, "Only me"),
        (ACCESS_AUTHENTICATED, "Any inference.club member"),
        (ACCESS_RESTRICTED, "Specific GitHub users"),
    )

    provider = models.ForeignKey(
        Provider, on_delete=models.CASCADE, related_name="services"
    )
    name = models.CharField(max_length=255)
    host_id = models.CharField(max_length=255, blank=True, help_text="Manifest host id, for display.")
    engine = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text="False when the service is no longer present in the latest manifest.",
    )
    access_policy = models.CharField(
        max_length=16, choices=ACCESS_POLICY_CHOICES, default=ACCESS_PRIVATE
    )
    allowed_github_users = models.JSONField(
        default=list,
        blank=True,
        help_text="GitHub usernames allowed when access_policy is RESTRICTED.",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "name"], name="unique_service_name_per_provider"
            )
        ]

    def __str__(self):
        return f"{self.provider}/{self.name}"

    def grants_access_to(self, user, github_login: str | None) -> bool:
        """Whether ``user`` (whose GitHub handle is ``github_login``) may route
        to this service. The owner always can; otherwise the policy decides."""
        if self.provider.user_id == getattr(user, "id", None):
            return True
        if not self.is_active:
            return False
        if self.access_policy == self.ACCESS_AUTHENTICATED:
            return True
        if self.access_policy == self.ACCESS_RESTRICTED:
            if not github_login:
                return False
            allowed = {u.strip().lower() for u in (self.allowed_github_users or [])}
            return github_login.strip().lower() in allowed
        return False  # PRIVATE


def slugify_model_id(value: str) -> str:
    """Normalize an HF repo id or served model name into the public, poolable
    model slug. Lowercasing is what collapses the *same* model served by many
    providers (and case variants of one id) into a single catalog entry, e.g.
    ``Qwen/Qwen3-30B-A3B`` → ``qwen/qwen3-30b-a3b``."""
    return (value or "").strip().lower()


class CatalogModel(BaseModel):
    """A logical model in the network catalog, identified by its HuggingFace
    repo id (or, for custom fine-tunes, a provider-declared name).

    Many ``ProviderModel`` deployments — across different providers, with
    different context windows / configs — point at one ``CatalogModel``. That
    pooling is what lets "the same model" aggregate into shared capacity
    instead of fragmenting into one catalog entry per provider.

    ``slug`` is the public model id callers pass to ``/v1`` (the lowercased HF
    id). Richer metadata (modalities, native context, recommended serving
    profile) is filled in by later phases; Phase 0 establishes identity +
    pooling only.
    """

    slug = models.CharField(max_length=255, unique=True)
    hf_repo_id = models.CharField(max_length=255, blank=True)
    display_name = models.CharField(max_length=255, blank=True)
    is_custom = models.BooleanField(
        default=False,
        help_text="True for models with no HuggingFace repo "
        "(custom fine-tunes / local-only weights).",
    )
    # --- Enrichment (Phase 2), synced from the HuggingFace Hub ---------------
    architecture = models.CharField(
        max_length=128, blank=True, help_text="e.g. 'Qwen2_5_VLForConditionalGeneration'."
    )
    native_context_length = models.PositiveIntegerField(
        null=True, blank=True, help_text="config.json max_position_embeddings (the ceiling)."
    )
    input_modalities = models.JSONField(default=list, blank=True)
    output_modalities = models.JSONField(default=list, blank=True)
    supported_features = models.JSONField(
        default=list, blank=True, help_text="e.g. ['reasoning', 'tools']."
    )
    hf_synced_at = models.DateTimeField(
        null=True, blank=True, help_text="Last successful HuggingFace enrichment."
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw HF subset (pipeline_tag, library_name, gated, downloads, "
        "likes, model_type) + future fields (recommended serving profile).",
    )

    class Meta:
        ordering = ["slug"]

    def __str__(self):
        return self.slug

    @property
    def hf_url(self) -> str:
        return f"https://huggingface.co/{self.hf_repo_id}" if self.hf_repo_id else ""


class ProviderModel(BaseModel):
    """An LLM model an agent reports it can serve — i.e. one *deployment* of a
    CatalogModel by a specific provider."""

    provider = models.ForeignKey(
        Provider, on_delete=models.CASCADE, related_name="models"
    )
    service = models.ForeignKey(
        ProviderService,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="models",
        help_text="The service that serves this model, when known from the "
        "manifest. Models discovered only via live /v1/models stay unlinked "
        "and remain owner-only.",
    )
    # ``name`` is the *served* id — the exact string this provider's backend
    # answers to (and what we forward upstream). It stays the per-provider key.
    name = models.CharField(max_length=255)
    hf_repo_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="The HuggingFace repo id this deployment serves, when "
        "declared (e.g. 'Qwen/Qwen3-30B-A3B'). Drives the catalog slug / "
        "pooling. Blank for live-discovered or custom models.",
    )
    catalog_model = models.ForeignKey(
        "CatalogModel",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deployments",
        help_text="The logical catalog model this deployment serves. Many "
        "providers' deployments share one CatalogModel — that pooling is what "
        "aggregates capacity for a model across the network.",
    )
    context_window = models.PositiveIntegerField(null=True, blank=True)
    # The served context window (vLLM's max_model_len), probed live from the
    # running server by the agent and reported via /v1/models. This is the
    # *real* per-deployment limit; surfaces ahead of the catalog's HF-derived
    # native length, and falls back to it (then blank) when unknown.
    served_context_len = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Operator-set overrides for the OpenRouter-style model "
        "catalog (e.g. name, quantization, context_length, max_output_length, "
        "input/output_modalities, supported_features, "
        "supported_sampling_parameters). Heuristics + defaults fill the rest.",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "name"], name="unique_model_name_per_provider"
            )
        ]

    def __str__(self):
        return f"{self.provider}/{self.name}"


def link_catalog_model(pm) -> "CatalogModel":
    """Point ``pm`` (a ProviderModel) at the right CatalogModel, creating or
    upgrading it from the declared HF id (preferred) or the served name.

    Sets ``pm.catalog_model`` but does NOT save ``pm`` — the caller persists.
    Returns the catalog model.
    """
    hf = (pm.hf_repo_id or "").strip()
    slug = slugify_model_id(hf or pm.name)
    catalog, _created = CatalogModel.objects.get_or_create(
        slug=slug,
        defaults={
            "hf_repo_id": hf,
            "display_name": hf or pm.name,
            "is_custom": not hf,
        },
    )
    # Upgrade a previously-custom entry once we learn its HF id.
    if hf and (catalog.is_custom or not catalog.hf_repo_id):
        catalog.hf_repo_id = hf
        catalog.is_custom = False
        if not catalog.display_name:
            catalog.display_name = hf
        catalog.save(
            update_fields=["hf_repo_id", "is_custom", "display_name", "modified_on"]
        )
    pm.catalog_model = catalog
    return catalog


class ServiceManifest(BaseModel):
    """The operator's description of their home network — hosts, GPUs, and
    LLM services running on each host.

    Uploaded by the agent via PUT /api/inference/agent/manifest/. Bound
    OneToOne to a Provider, looked up by ``(user, agent.name)``. Both the
    raw YAML and the parsed JSON are stored: parsed is what the UI renders,
    raw is what the operator wrote (so the dashboard can show it back to
    them verbatim).

    Manifests that fail server-side validation are still persisted with
    ``is_valid=False`` and a list of errors, so the dashboard can show
    "your manifest is broken, here's why" instead of "no manifest yet."
    """

    provider = models.OneToOneField(
        "Provider",
        on_delete=models.CASCADE,
        related_name="manifest",
    )
    schema_version = models.PositiveSmallIntegerField(default=1)
    raw_yaml = models.TextField(
        help_text="The YAML the operator wrote, stored verbatim for re-display."
    )
    parsed = models.JSONField(
        help_text="Validated structured form. UI renders from this; "
        "no YAML parser runs in the browser."
    )
    uploaded_at = models.DateTimeField(auto_now=True)
    is_valid = models.BooleanField(default=True)
    validation_errors = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"manifest for {self.provider}"


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
    # Time to first token (streamed requests only) — an OpenRouter-style
    # performance signal. Throughput is derived from completion_tokens and
    # (latency_ms - ttft_ms).
    ttft_ms = models.PositiveIntegerField(null=True, blank=True)
    # Token usage, mirrored from the response's `usage` for cheap aggregation
    # (leaderboard, quotas) without parsing the results JSON. Null when the
    # provider didn't report usage (e.g. streamed without stream_options).
    prompt_tokens = models.PositiveIntegerField(null=True, blank=True)
    completion_tokens = models.PositiveIntegerField(null=True, blank=True)
    total_tokens = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_on"]
        indexes = [
            models.Index(fields=["user", "status", "created_on"]),
            # Powers the leaderboard's time-windowed token aggregation.
            models.Index(fields=["created_on"], name="ir_created_on_idx"),
        ]

    def __str__(self):
        return f"{self.inference_type} request by {self.user.username} ({self.status})"
