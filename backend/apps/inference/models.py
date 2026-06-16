import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import BaseModel

# How long after the last successful proxy / probe a provider stays "online"
# without any new evidence. Two minutes leaves room for occasional latency
# spikes without flapping the UI.
PROVIDER_LAST_SEEN_WINDOW = timedelta(seconds=120)


# --- Content visibility (see docs/prd/01-content-sharing.md) -----------------
# One axis shared by InferenceRequest and Collection. The owner always sees
# their own content regardless of level.
#
#   PUBLIC   — anyone (even logged-out); listed on the owner's public profile.
#   UNLISTED — anyone with the link (the unguessable share_token); NOT listed
#              on the public profile or in network listings.
#   PRIVATE  — any signed-in inference.club member; not listed publicly.
#   SECRET   — only the owner ("Only me").
VISIBILITY_PUBLIC = "PUBLIC"
VISIBILITY_UNLISTED = "UNLISTED"
VISIBILITY_PRIVATE = "PRIVATE"
VISIBILITY_SECRET = "SECRET"
VISIBILITY_CHOICES = (
    (VISIBILITY_PUBLIC, "Public"),
    (VISIBILITY_UNLISTED, "Unlisted"),
    (VISIBILITY_PRIVATE, "Members only"),
    (VISIBILITY_SECRET, "Only me"),
)
VISIBILITY_VALUES = {c[0] for c in VISIBILITY_CHOICES}
# New content defaults to unlisted unless the owner picked another default.
DEFAULT_VISIBILITY = VISIBILITY_UNLISTED


def generate_share_token() -> str:
    """An unguessable, URL-safe token used to resolve a request by link, so
    UNLISTED/PRIVATE content can't be enumerated via the sequential PK."""
    return secrets.token_urlsafe(16)


def _is_member_viewer(user) -> bool:
    """Authenticated full member. Guest/passcode accounts don't qualify for
    the PRIVATE ("members only") tier — they see what the public sees, plus
    their own content."""
    return bool(
        user is not None
        and getattr(user, "is_authenticated", False)
        and not getattr(user, "is_anonymous_account", False)
    )


def visible_list_q(user) -> Q:
    """A ``Q`` selecting requests that may appear in *listings* (the
    network-wide feed, profiles). UNLISTED and SECRET are deliberately
    excluded — they're reachable only by direct link/owner. Direct access
    (by token or PK) uses ``InferenceRequest.is_visible_to`` instead, which is
    more permissive for the link case."""
    if _is_member_viewer(user):
        return Q(user=user) | Q(
            visibility__in=[VISIBILITY_PUBLIC, VISIBILITY_PRIVATE]
        )
    if user is not None and getattr(user, "is_authenticated", False):
        # Anonymous account: own content + PUBLIC only.
        return Q(user=user) | Q(visibility=VISIBILITY_PUBLIC)
    return Q(visibility=VISIBILITY_PUBLIC)


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

    # What kind of inference the service provides — the *what*, orthogonal to
    # ``engine`` (the *how*). Drives which /v1 endpoint a request may route to:
    # an STT (transcription) request never lands on an LLM service and vice
    # versa. Declared in the manifest as ``services[].type``; defaults to
    # ``llm`` so every existing manifest stays valid.
    TYPE_LLM = "llm"
    TYPE_STT = "stt"
    TYPE_TTS = "tts"
    TYPE_IMAGE = "image"
    TYPE_MESH = "mesh"
    TYPE_MUSIC = "music"
    TYPE_VIDEO = "video"
    # --- media pipeline service types (PRD 12) ---
    # Authorable + routable today; a provider serves them by declaring the type
    # in its manifest. Until one does, steps using them queue (like any modality
    # with no provider). Runners are deferred — the agent-side handlers are the
    # remaining work.
    TYPE_SCRAPE = "scrape"  # URL → document (Firecrawl), `scrape` node
    TYPE_RENDER = "render"  # images+audio+subs → video (FFmpeg), `compose` node
    TYPE_AUDIO_ENHANCE = "audio-enhance"  # denoise/clean (StudioVoice), `clean` node
    SERVICE_TYPE_CHOICES = (
        (TYPE_LLM, "Language model"),
        (TYPE_STT, "Speech to text"),
        (TYPE_TTS, "Text to speech"),
        (TYPE_IMAGE, "Image generation"),
        (TYPE_MESH, "Image to 3D"),
        (TYPE_MUSIC, "Music generation"),
        (TYPE_VIDEO, "Video generation"),
        (TYPE_SCRAPE, "Web scrape"),
        (TYPE_RENDER, "Video compose"),
        (TYPE_AUDIO_ENHANCE, "Audio enhancement"),
    )

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
    service_type = models.CharField(
        max_length=16, choices=SERVICE_TYPE_CHOICES, default=TYPE_LLM
    )
    declared_features = models.JSONField(
        default=list,
        blank=True,
        help_text="Operator-declared capabilities of THIS deployment, from the "
        "manifest's services[].features (e.g. ['timestamps'] when an STT "
        "service is served with a ForcedAligner so verbose_json returns word "
        "timings). Per-deployment because the same model may or may not expose "
        "a feature depending on how it was launched.",
    )
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
    # --- Async queue capacity (see docs/prd/10-async-jobs-and-workflows.md) ---
    # How many *queued* (async) jobs this service may run at once. Declared in
    # the manifest as services[].max_concurrent; defaults to 1 (safe for a
    # single-GPU box). Does not gate synchronous, user-blocking requests.
    max_concurrent = models.PositiveIntegerField(default=1)
    # Optional named pool this service draws slots from. Services sharing a
    # resource_group within one provider contend for a single ResourceGroup
    # slot budget — this is how "two services on one GPU, only one at a time"
    # is expressed (declared in the manifest's services[].resource_group).
    resource_group = models.CharField(max_length=64, blank=True, default="")

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
    # --- Capabilities, declared by the operator in the agent manifest --------
    # (modalities default from the service type when a model omits them). The
    # native context length is the declared ceiling; the live-probed
    # ProviderModel.served_context_len takes precedence when present.
    native_context_length = models.PositiveIntegerField(
        null=True, blank=True, help_text="Declared context-window ceiling."
    )
    input_modalities = models.JSONField(default=list, blank=True)
    output_modalities = models.JSONField(default=list, blank=True)
    supported_features = models.JSONField(
        default=list, blank=True, help_text="e.g. ['reasoning', 'tools']."
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Operator-declared extras (e.g. recommended serving profile).",
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
        "supported_sampling_parameters). The linked catalog model + defaults "
        "fill the rest.",
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


class ManifestRevision(BaseModel):
    """Append-only history of a provider's valid manifests (PRD 07 V3,
    story mode). ServiceManifest is OneToOne — only the latest survives — so
    time-scrubbing needs its own table. A revision is recorded on every
    accepted upload whose ``parsed`` differs from the previous revision (the
    agent re-pushes on restart; identical bodies would just be noise).

    Only valid manifests are recorded: history is "what the cluster looked
    like", not "what the operator mistyped".
    """

    provider = models.ForeignKey(
        Provider,
        on_delete=models.CASCADE,
        related_name="manifest_revisions",
    )
    schema_version = models.PositiveSmallIntegerField(default=1)
    parsed = models.JSONField()
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return f"manifest revision {self.id} for {self.provider}"

    @classmethod
    def record(cls, provider, parsed, schema_version=1):
        """Append a revision unless it matches the provider's latest one.
        Returns the revision or None when skipped as a duplicate."""
        latest = cls.objects.filter(provider=provider).order_by("-uploaded_at").first()
        if latest is not None and latest.parsed == parsed:
            return None
        return cls.objects.create(
            provider=provider, parsed=parsed, schema_version=schema_version
        )


class InferenceRequest(BaseModel):
    INFERENCE_TYPES = (
        ("LLM", "Language Model"),
        ("STT", "Speech to Text"),
        ("IMAGE", "Image Generation"),
        ("VIDEO", "Video Generation"),
        ("TTS", "Text to Speech"),
        ("MESH", "Image to 3D"),
        ("MUSIC", "Music Generation"),
        ("VOICE", "Voice Cloning"),
        # --- media pipeline (PRD 12); runners deferred to the agent ---
        ("SCRAPE", "Web Scrape"),
        ("RENDER", "Video Compose"),
        ("ENHANCE", "Audio Enhancement"),
    )

    STATUS_CHOICES = (
        ("REQUESTED", "Requested"),
        ("QUEUED", "Queued"),
        ("PROCESSING", "Processing"),
        ("PROCESSED", "Processed"),
        ("FAILED", "Failed"),
        ("CANCELED", "Canceled"),
        ("SAVED", "Saved"),
    )
    # Terminal states an async job can't leave (the dispatcher ignores them).
    TERMINAL_STATUSES = ("PROCESSED", "FAILED", "CANCELED")

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
    # Audio metering for non-text modalities (STT, later TTS) — the analogue of
    # token counts for audio. Mirrored from the response's ``usage.seconds`` (or
    # the probed input-audio duration) for cheap aggregation without parsing
    # the results JSON. Null for LLM requests.
    audio_seconds = models.FloatField(null=True, blank=True)
    # Image metering — how many images this request produced. The analogue of
    # tokens/seconds for image generation; null for non-image requests.
    image_count = models.PositiveIntegerField(null=True, blank=True)

    # --- Async queue / jobs (see docs/prd/10-async-jobs-and-workflows.md) ----
    # An async job IS an InferenceRequest created in QUEUED state and run later
    # by a worker when a capacity slot frees up — same row, same finalization
    # as a synchronous request. These fields are inert for sync requests
    # (is_async=False), so the live inference path is unchanged.
    is_async = models.BooleanField(default=False, db_index=True)
    # The routing service type the dispatcher resolves a provider against
    # (e.g. "image"); blank means the LLM path (no restriction).
    job_service_type = models.CharField(max_length=16, blank=True, default="")
    queued_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    # The dispatcher skips the job until this time — used for retry backoff.
    run_after = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    # Higher priority dispatches first; ties broken by queued_at (FIFO).
    priority = models.SmallIntegerField(default=0)
    # Optional per-user idempotency key: a duplicate submit returns the
    # existing job instead of creating a second (safe agent resubmits).
    idempotency_key = models.CharField(max_length=128, blank=True, default="")
    # Structured last-failure detail (message + classification), distinct from
    # `results` which holds the upstream body.
    error = models.JSONField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    # Internal scheduling breadcrumbs (resolved served name, service id, etc.).
    dispatch_meta = models.JSONField(default=dict, blank=True)
    # Grouping: a job may belong to a Batch (submitted together) and/or a
    # workflow step (a node in a DAG). Both null for a standalone job.
    batch = models.ForeignKey(
        "Batch", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="jobs",
    )
    step_run = models.ForeignKey(
        "WorkflowStepRun", null=True, blank=True, on_delete=models.CASCADE,
        related_name="jobs",
    )

    # --- Sharing & curation (see docs/prd/01-content-sharing.md) ------------
    # Who may see this request. Left blank on the model so save() can fill it
    # from the owner's account default; the data migration backfills existing
    # rows to PUBLIC (preserving the prior all-public-profile behavior).
    visibility = models.CharField(
        max_length=12, choices=VISIBILITY_CHOICES, blank=True, db_index=True
    )
    # Unguessable handle for link-based access (so UNLISTED/PRIVATE content
    # isn't enumerable via the sequential id). Set on create, rotatable.
    # unique=True already creates the lookup index; adding db_index=True too
    # makes postgres build a duplicate varchar_pattern_ops "_like" index whose
    # name collides during the add→alter migration step, so keep just unique.
    share_token = models.CharField(max_length=32, unique=True, editable=False)
    # Denormalized star total, for cheap "most popular" sorting.
    star_count = models.PositiveIntegerField(default=0, db_index=True)
    # Optional cover art — a linked IMAGE request whose output renders as this
    # request's square artwork (MUSIC tracks, Spotify-style). SET_NULL so
    # deleting the art request only clears the cover, never the track.
    cover_request = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    # Staff curation for the public home page: set = featured (when it was
    # featured), null = not. The showcase pulls the most recently featured
    # PUBLIC request per inference_type; only staff may toggle it.
    featured_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_on"]
        indexes = [
            models.Index(fields=["user", "status", "created_on"]),
            # Powers the leaderboard's time-windowed token aggregation.
            models.Index(fields=["created_on"], name="ir_created_on_idx"),
            # Powers the dispatcher's "next queued job" scan.
            models.Index(
                fields=["is_async", "status", "priority", "queued_at"],
                name="ir_dispatch_idx",
            ),
        ]
        constraints = [
            # One job per (user, idempotency_key) — a resubmit returns the
            # existing job rather than creating a duplicate. Partial: blank
            # keys (every sync/non-idempotent request) are unconstrained.
            models.UniqueConstraint(
                fields=["user", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="unique_idempotency_key_per_user",
            )
        ]

    def __str__(self):
        return f"{self.inference_type} request by {self.user.username} ({self.status})"

    def _account_default_visibility(self) -> str:
        """The owner's chosen default visibility for new requests, falling back
        to the global default. Read off the already-loaded ``user`` so create
        paths (which pass ``user=...``) incur no extra query."""
        return (
            getattr(self.user, "default_request_visibility", "") or DEFAULT_VISIBILITY
        )

    def save(self, *args, **kwargs):
        if self._state.adding:
            if not self.visibility:
                self.visibility = self._account_default_visibility()
            # Anonymous accounts can never publish publicly — clamp at the
            # model so every create path (proxy, playground, API) is covered.
            if self.visibility == VISIBILITY_PUBLIC and getattr(
                self.user, "is_anonymous_account", False
            ):
                self.visibility = VISIBILITY_UNLISTED
            if not self.share_token:
                self.share_token = generate_share_token()
        super().save(*args, **kwargs)

    def is_visible_to(self, user) -> bool:
        """Whether ``user`` may *directly access* this request (by share link or
        PK). More permissive than ``visible_list_q`` for the UNLISTED link case:
        anyone holding the link/id may open an UNLISTED request."""
        if (
            user is not None
            and getattr(user, "is_authenticated", False)
            and self.user_id == user.id
        ):
            return True  # the owner always can
        if self.visibility in (VISIBILITY_PUBLIC, VISIBILITY_UNLISTED):
            return True
        if self.visibility == VISIBILITY_PRIVATE:
            # "Members only" means full members — guest/passcode accounts
            # count as the public here.
            return _is_member_viewer(user)
        return False  # SECRET — owner only

    def recount_stars(self) -> int:
        """Recompute and persist ``star_count`` from the Star rows."""
        self.star_count = self.stars.count()
        type(self).objects.filter(pk=self.pk).update(star_count=self.star_count)
        return self.star_count


def media_asset_upload_to(instance, filename: str) -> str:
    """Storage key for a media asset: ``<kind>/<user_id>/<uuid>/<filename>``.

    Namespaced by kind + user so a single bucket cleanly holds input audio
    (STT), and later generated audio (TTS) and images, without collisions.
    """
    import uuid

    safe = (filename or "asset").rsplit("/", 1)[-1][:120]
    return f"{instance.kind.lower()}/{instance.user_id}/{uuid.uuid4().hex}/{safe}"


class MediaAsset(BaseModel):
    """A binary blob stored in object storage (S3/MinIO in prod, local FS in
    dev) tied to a user and, usually, an inference request.

    Built generic on purpose: STT stores the uploaded ``INPUT_AUDIO`` here so
    the playground/profile can replay it, and the next modalities reuse the
    same model — TTS writes ``OUTPUT_AUDIO`` and image generation
    ``OUTPUT_IMAGE``. The ``file`` field routes through Django's default
    storage backend, so swapping FS ↔ S3 is a settings change, not a code one.
    """

    INPUT_AUDIO = "INPUT_AUDIO"
    OUTPUT_AUDIO = "OUTPUT_AUDIO"
    INPUT_IMAGE = "INPUT_IMAGE"
    OUTPUT_IMAGE = "OUTPUT_IMAGE"
    OUTPUT_MODEL = "OUTPUT_MODEL"  # generated 3D mesh (GLB), image-to-3D
    OUTPUT_VIDEO = "OUTPUT_VIDEO"  # generated video (MP4), text/image-to-video
    # --- media pipeline (PRD 12) ---
    INPUT_DOC = "INPUT_DOC"  # scraped source document (markdown), `scrape` node
    OUTPUT_DOC = "OUTPUT_DOC"  # generated text/script (e.g. [S1]/[S2] dialog)
    OUTPUT_SUBTITLE = "OUTPUT_SUBTITLE"  # ASS/VTT subtitle track, `subtitle` node
    KIND_CHOICES = (
        (INPUT_AUDIO, "Input audio"),
        (OUTPUT_AUDIO, "Output audio"),
        (INPUT_IMAGE, "Input image"),
        (OUTPUT_IMAGE, "Output image"),
        (OUTPUT_MODEL, "Output 3D model"),
        (OUTPUT_VIDEO, "Output video"),
        (INPUT_DOC, "Input document"),
        (OUTPUT_DOC, "Output document"),
        (OUTPUT_SUBTITLE, "Output subtitle"),
    )
    # Kinds served publicly (by URL, no auth) so generated images/audio/3D
    # models/videos/subtitles embed in <img>/<audio>/<model-viewer>/<video>/
    # <track> tags and show on profiles. Generated output is open by default;
    # uploaded input audio (STT) and source/output documents stay
    # owner-gated/private.
    PUBLIC_KINDS = {
        INPUT_IMAGE, OUTPUT_IMAGE, OUTPUT_AUDIO, OUTPUT_MODEL, OUTPUT_VIDEO,
        OUTPUT_SUBTITLE,
    }

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="media_assets",
    )
    inference_request = models.ForeignKey(
        InferenceRequest,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assets",
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    file = models.FileField(upload_to=media_asset_upload_to, max_length=512)
    content_type = models.CharField(max_length=128, blank=True, default="")
    size_bytes = models.BigIntegerField(null=True, blank=True)
    duration_seconds = models.FloatField(
        null=True, blank=True, help_text="Audio/video duration, when known."
    )
    metadata = models.JSONField(default=dict, blank=True)
    # --- provenance (PRD 12 §5.1) ---
    # The upstream asset(s) this one was produced from — an OUTPUT_VIDEO derives
    # from its images + audio + subtitle; an image-to-image frame from its
    # parent. Combined with ``inference_request`` (which job + prompt/params
    # made it), this lets any artifact be traced back to its component parts.
    derived_from = models.ManyToManyField(
        "self", symmetrical=False, related_name="derivatives", blank=True,
    )

    class Meta:
        ordering = ["-created_on"]
        indexes = [
            models.Index(fields=["user", "kind", "created_on"]),
        ]

    def __str__(self):
        return f"{self.kind} asset {self.pk} for {self.user_id}"

    def record_derivation(self, sources) -> None:
        """Record that this asset was produced from ``sources`` (MediaAsset
        instances or ids). Idempotent; ignores self-links and falsy ids."""
        ids = [getattr(s, "pk", s) for s in (sources or [])]
        ids = [i for i in ids if i and i != self.pk]
        if ids:
            self.derived_from.add(*ids)


class VoiceSample(BaseModel):
    """A user-owned reference voice for cloning with Dia (see
    docs/prd/09-voice-cloning.md).

    A "speaker" isn't its own table — it's the set of samples sharing
    ``(user, speaker_name)``. Each speaker has exactly one **default** sample
    (``is_default``) plus zero or more **variations**. Cloning needs *both* the
    audio and its transcript, so ``transcript`` is filled in — auto via our own
    STT, or by hand. Private by design: the clip is an ``INPUT_AUDIO``
    ``MediaAsset`` (owner-gated, never in ``PUBLIC_KINDS``), so a voice print is
    never served publicly in V1.
    """

    SOURCE_STT = "stt"
    SOURCE_MANUAL = "manual"
    SOURCE_EDITED = "edited"
    TRANSCRIPT_SOURCES = (
        (SOURCE_STT, "Auto (speech-to-text)"),
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_EDITED, "Edited"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="voice_samples",
    )
    speaker_name = models.CharField(max_length=120)
    # A short variation name ("warm", "fast"); blank for the default sample.
    label = models.CharField(max_length=120, blank=True, default="")
    is_default = models.BooleanField(default=False)
    # CASCADE: deleting the sample drops its private audio blob with it.
    audio = models.ForeignKey(
        MediaAsset, on_delete=models.CASCADE, related_name="voice_samples"
    )
    transcript = models.TextField(blank=True, default="")
    transcript_source = models.CharField(
        max_length=8, choices=TRANSCRIPT_SOURCES, default=SOURCE_MANUAL
    )
    language = models.CharField(max_length=16, blank=True, default="")
    duration_seconds = models.FloatField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["speaker_name", "-is_default", "-created_on"]
        constraints = [
            # At most one default sample per (user, speaker). Promoting a new
            # default clears the old one in the same transaction (see the view).
            models.UniqueConstraint(
                fields=["user", "speaker_name"],
                condition=models.Q(is_default=True),
                name="one_default_voice_sample_per_speaker",
            )
        ]
        indexes = [
            models.Index(fields=["user", "speaker_name", "created_on"]),
        ]

    def __str__(self):
        return f"voice {self.speaker_name!r} sample {self.pk} for {self.user_id}"


class Star(BaseModel):
    """A user "starred" (liked) a request. The like signal + popularity stat;
    we expose aggregate counts only, never *who* starred."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="stars"
    )
    request = models.ForeignKey(
        InferenceRequest, on_delete=models.CASCADE, related_name="stars"
    )

    class Meta:
        ordering = ["-created_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "request"], name="unique_star_per_user_request"
            )
        ]

    def __str__(self):
        return f"star u{self.user_id}->r{self.request_id}"


class Bookmark(BaseModel):
    """A user saved a request to surface on their public profile. Distinct from
    a Star: a curation choice ("show this on my profile"), not a like."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookmarks"
    )
    request = models.ForeignKey(
        InferenceRequest, on_delete=models.CASCADE, related_name="bookmarks"
    )

    class Meta:
        ordering = ["-created_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "request"], name="unique_bookmark_per_user_request"
            )
        ]

    def __str__(self):
        return f"bookmark u{self.user_id}->r{self.request_id}"


class Collection(BaseModel):
    """A user-named group of inference requests. A request may live in zero,
    one, or many collections; ``visibility`` controls who sees the collection
    itself (items inside still enforce their own visibility)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="collections",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    description = models.TextField(blank=True, default="")
    visibility = models.CharField(
        max_length=12, choices=VISIBILITY_CHOICES, default=DEFAULT_VISIBILITY
    )
    # Optional cover; SET_NULL (not CASCADE) so deleting the request just clears
    # the cover rather than the whole collection.
    cover_request = models.ForeignKey(
        InferenceRequest,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "slug"], name="unique_collection_slug_per_user"
            )
        ]

    def __str__(self):
        return f"{self.user_id}:{self.slug}"


class CollectionItem(BaseModel):
    """Membership of a request in a collection (the M2M through-model)."""

    collection = models.ForeignKey(
        Collection, on_delete=models.CASCADE, related_name="items"
    )
    request = models.ForeignKey(
        InferenceRequest, on_delete=models.CASCADE, related_name="collection_items"
    )
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "-created_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "request"], name="unique_request_per_collection"
            )
        ]

    def __str__(self):
        return f"c{self.collection_id}<-r{self.request_id}"


# --- Content moderation ------------------------------------------------------
# Members can flag an inference request for inappropriate content; staff triage
# the queue from the in-app admin surface. See the staff_views module.
REPORT_REASON_CHOICES = (
    ("SEXUAL", "Sexual or explicit content"),
    ("VIOLENCE", "Violence or gore"),
    ("HATE", "Hate or harassment"),
    ("ILLEGAL", "Illegal or dangerous"),
    ("CSAM", "Child sexual abuse material"),
    ("SPAM", "Spam or misleading"),
    ("OTHER", "Other"),
)

REPORT_STATUS_OPEN = "OPEN"
REPORT_STATUS_REVIEWING = "REVIEWING"
REPORT_STATUS_RESOLVED = "RESOLVED"
REPORT_STATUS_DISMISSED = "DISMISSED"
REPORT_STATUS_CHOICES = (
    (REPORT_STATUS_OPEN, "Open"),
    (REPORT_STATUS_REVIEWING, "Reviewing"),
    (REPORT_STATUS_RESOLVED, "Resolved"),
    (REPORT_STATUS_DISMISSED, "Dismissed"),
)
# Statuses that still need staff attention (drive the moderation queue badge).
REPORT_OPEN_STATUSES = (REPORT_STATUS_OPEN, REPORT_STATUS_REVIEWING)


class ContentReport(BaseModel):
    """A member's report that an inference request contains inappropriate
    content. One open report per (reporter, request) — re-reporting is a no-op.

    Reports are never auto-deleted with their reporter (SET_NULL): the moderation
    record should outlive an account removal. They *are* deleted with the
    request (CASCADE) — once the content is gone there's nothing left to moderate.
    """

    request = models.ForeignKey(
        InferenceRequest,
        on_delete=models.CASCADE,
        related_name="reports",
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="filed_reports",
    )
    reason = models.CharField(max_length=16, choices=REPORT_REASON_CHOICES)
    details = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=REPORT_STATUS_CHOICES,
        default=REPORT_STATUS_OPEN,
        db_index=True,
    )
    # Staff triage outcome.
    resolution_note = models.TextField(blank=True, default="")
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_reports",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["reporter", "request"],
                name="unique_report_per_reporter_request",
            )
        ]
        indexes = [
            models.Index(fields=["status", "created_on"]),
        ]

    def __str__(self):
        return f"report#{self.pk} r{self.request_id} [{self.status}]"


# --- Async jobs, batches & workflows -----------------------------------------
# See docs/prd/10-async-jobs-and-workflows.md. A "job" is just an
# InferenceRequest with is_async=True (above). Batches group jobs submitted
# together; workflows arrange jobs into a dependency graph.


class ResourceGroup(BaseModel):
    """A named slot pool on one provider. Services that declare the same
    ``resource_group`` contend for this group's ``max_concurrent`` budget — the
    way "two services on one GPU, only one at a time" is modeled. Mirrored from
    the manifest's top-level ``resource_groups`` on every accepted upload.
    """

    provider = models.ForeignKey(
        Provider, on_delete=models.CASCADE, related_name="resource_groups"
    )
    name = models.CharField(max_length=64)
    max_concurrent = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "name"], name="unique_resource_group_per_provider"
            )
        ]

    def __str__(self):
        return f"{self.provider}/group:{self.name}"


class Batch(BaseModel):
    """A set of jobs submitted together in one ``POST /v1/batches`` call. The
    batch has no status column of its own — it's derived from its member jobs
    (see ``aggregate_status``) so it can never drift out of sync."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="batches"
    )
    label = models.CharField(max_length=160, blank=True, default="")

    class Meta:
        ordering = ["-created_on"]

    def __str__(self):
        return f"batch#{self.pk} ({self.label or 'unlabeled'})"

    def aggregate_status(self) -> str:
        """Roll the member jobs' statuses up into one batch status."""
        statuses = list(self.jobs.values_list("status", flat=True))
        if not statuses:
            return "EMPTY"
        if any(s in ("QUEUED", "PROCESSING") for s in statuses):
            return "RUNNING"
        done = sum(1 for s in statuses if s == "PROCESSED")
        failed = any(s in ("FAILED", "CANCELED") for s in statuses)
        if done == len(statuses):
            return "DONE"
        if done == 0 and failed:
            return "FAILED"
        return "PARTIAL"


# Workflow run / step lifecycle states. Steps and runs share most labels so the
# DAG viewer can color them uniformly.
WF_PENDING = "PENDING"        # not yet eligible (deps unmet) / not started
WF_RUNNING = "RUNNING"        # jobs dispatched / in flight
WF_AWAITING = "AWAITING"      # a human gate is blocking
WF_DONE = "DONE"
WF_FAILED = "FAILED"
WF_CANCELED = "CANCELED"
WF_SKIPPED = "SKIPPED"        # an upstream failure pruned this branch
WF_STATUS_CHOICES = (
    (WF_PENDING, "Pending"),
    (WF_RUNNING, "Running"),
    (WF_AWAITING, "Awaiting input"),
    (WF_DONE, "Done"),
    (WF_FAILED, "Failed"),
    (WF_CANCELED, "Canceled"),
    (WF_SKIPPED, "Skipped"),
)

# Step kinds (see the workflow engine). inference → one job; map → one job per
# item of an upstream list; transform/collect → pure data steps run inline;
# gate → pause for human approval.
STEP_INFERENCE = "inference"
STEP_MAP = "map"
STEP_TRANSFORM = "transform"
STEP_COLLECT = "collect"
STEP_GATE = "gate"
STEP_KIND_CHOICES = (
    (STEP_INFERENCE, "Inference"),
    (STEP_MAP, "Map (fan-out)"),
    (STEP_TRANSFORM, "Transform"),
    (STEP_COLLECT, "Collect"),
    (STEP_GATE, "Human gate"),
)


class Workflow(BaseModel):
    """A reusable DAG definition (a ``spec``) authored by a human or an agent.
    A run snapshots the spec, so editing a Workflow never mutates history."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workflows"
    )
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    spec = models.JSONField(default=dict)

    class Meta:
        ordering = ["-modified_on"]

    def __str__(self):
        return f"workflow {self.name!r} (u{self.user_id})"


class WorkflowRun(BaseModel):
    """One execution of a workflow spec. ``context`` accumulates each step's
    output so later steps can template against it; the DAG viewer polls this."""

    workflow = models.ForeignKey(
        Workflow, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="runs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workflow_runs"
    )
    name = models.CharField(max_length=160, blank=True, default="")
    # The spec actually run (snapshot, so it's immutable for this run).
    spec = models.JSONField(default=dict)
    inputs = models.JSONField(default=dict, blank=True)
    # {"inputs": {...}, "steps": {step_id: <output>}} — the templating scope.
    context = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=12, choices=WF_STATUS_CHOICES, default=WF_PENDING, db_index=True
    )
    error = models.JSONField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_on"]

    def __str__(self):
        return f"run#{self.pk} of {self.name or 'workflow'} [{self.status}]"


class WorkflowStepRun(BaseModel):
    """One node in a run's DAG. Edges are the ``depends_on`` step ids. The jobs
    a step spawns point back via ``InferenceRequest.step_run``."""

    run = models.ForeignKey(
        WorkflowRun, on_delete=models.CASCADE, related_name="steps"
    )
    step_id = models.CharField(max_length=64)
    kind = models.CharField(max_length=16, choices=STEP_KIND_CHOICES)
    title = models.CharField(max_length=160, blank=True, default="")
    depends_on = models.JSONField(default=list, blank=True)
    # The step definition from the spec (endpoint, body template, over, op, …).
    spec = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=12, choices=WF_STATUS_CHOICES, default=WF_PENDING, db_index=True
    )
    # The step's produced value, merged into the run context under this step id.
    output = models.JSONField(null=True, blank=True)
    error = models.JSONField(null=True, blank=True)
    position = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "step_id"], name="unique_step_id_per_run"
            )
        ]

    def __str__(self):
        return f"step {self.step_id!r} of run#{self.run_id} [{self.status}]"


class WorkflowPromptSuggestion(models.Model):
    """LLM-generated high-level prompts for workflow templates.

    Populated by the ``generate_workflow_prompts`` management command, which
    calls a local chat model once and bulk-inserts the results. The API
    endpoint samples N rows at random so the gallery always shows fresh ideas.
    """

    template_key = models.CharField(max_length=64, db_index=True)
    text = models.TextField()
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.template_key}: {self.text[:60]}"


# --- Narration Studio (PRD 12 §5.3/§5.4) -------------------------------------


class Episode(BaseModel):
    """A narration project: an ordered list of ``Segment``s a user voices,
    reviews and polishes in the Studio. Born either from a media-pipeline
    ``WorkflowRun`` (Track A) or created by hand (Track B) — same model, two
    front doors."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="episodes"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    # The run that seeded this episode, if any (Track A).
    workflow_run = models.ForeignKey(
        WorkflowRun, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="episodes",
    )
    # Default voice for the whole episode. ``voice_model`` is the chosen TTS /
    # voice model name ("" = auto-pick the first reachable voice-cloning model);
    # ``voice_sample`` is the Dia reference clip to clone (ignored by plain TTS).
    # A Segment may still override the sample via its own ``voice_sample``.
    voice_model = models.CharField(max_length=200, blank=True, default="")
    voice_sample = models.ForeignKey(
        "VoiceSample", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="episodes",
    )

    class Meta:
        ordering = ["-modified_on"]

    def __str__(self):
        return f"episode {self.title!r} (u{self.user_id})"


class Segment(BaseModel):
    """One narration unit in an Episode — the text to speak plus its takes
    (``Variant``s). The active take is ``selected_variant``; regenerating adds a
    new Variant (non-destructive retakes, à la inference-club-studio)."""

    STATUS_PENDING = "pending"
    STATUS_QUEUED = "queued"     # dispatched, waiting for the device (per-device serialized)
    STATUS_GENERATING = "generating"
    STATUS_READY = "ready"
    STATUS_FLAGGED = "flagged"   # audio produced, but grading flagged the take
    STATUS_ERROR = "error"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_GENERATING, "Generating"),
        (STATUS_READY, "Ready"),
        (STATUS_FLAGGED, "Flagged"),
        (STATUS_ERROR, "Error"),
    )

    episode = models.ForeignKey(
        Episode, on_delete=models.CASCADE, related_name="segments"
    )
    position = models.PositiveIntegerField(default=0)
    text = models.TextField()
    # Pre-edit text, so an edit can be undone (the Studio shows this).
    original_text = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    # The take currently used for playback/export.
    selected_variant = models.ForeignKey(
        "Variant", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    # Per-segment Dia voice override (PRD 09); blank = the episode/account default.
    voice_sample = models.ForeignKey(
        VoiceSample, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"segment #{self.position} of episode#{self.episode_id}"


class Variant(BaseModel):
    """One take of a ``Segment`` — a generated audio clip plus its provenance
    (the job that made it), word timestamps, and an optional StudioVoice-cleaned
    copy kept *separate* from the original so cleaning is never destructive."""

    CLEAN_NOT = "not_cleaned"
    CLEAN_DONE = "cleaned"
    CLEAN_UNAVAILABLE = "unavailable"
    CLEAN_ERROR = "error"
    CLEAN_CHOICES = (
        (CLEAN_NOT, "Not cleaned"),
        (CLEAN_DONE, "Cleaned"),
        (CLEAN_UNAVAILABLE, "Unavailable"),
        (CLEAN_ERROR, "Error"),
    )

    segment = models.ForeignKey(
        Segment, on_delete=models.CASCADE, related_name="variants"
    )
    # The text actually voiced for this take (may differ once the segment is
    # edited and regenerated).
    text = models.TextField(blank=True, default="")
    audio = models.ForeignKey(
        MediaAsset, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    inference_request = models.ForeignKey(
        InferenceRequest, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    duration_seconds = models.FloatField(null=True, blank=True)
    # Word-level timestamps aligned to the processed audio: [{word, start, end}].
    words = models.JSONField(default=list, blank=True)
    # The processed audio (StudioVoice-cleaned + silence/pause-trimmed), kept
    # beside the untouched original (``audio``) so cleaning is never destructive.
    cleaned_audio = models.ForeignKey(
        MediaAsset, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    # The StudioVoice-cleaned audio *before* trimming — the canonical timeline the
    # Studio waveform editor draws and places trim regions against. ``cleaned_audio``
    # is this minus ``trim_intervals``; keeping both lets the editor show the diff
    # (what was clipped) and re-cut from scratch on a manual re-trim.
    enhanced_audio = models.ForeignKey(
        MediaAsset, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    # Word timestamps on the *enhanced* (untrimmed) timeline: [{word, start, end}].
    enhanced_words = models.JSONField(default=list, blank=True)
    # Keep-ranges [[start, end], …] (seconds, on the enhanced timeline) that were
    # kept to produce ``cleaned_audio``. The removed regions are the gaps between
    # them — that's the trim "diff" the editor renders and the user can edit.
    trim_intervals = models.JSONField(default=list, blank=True)
    clean_status = models.CharField(
        max_length=12, choices=CLEAN_CHOICES, default=CLEAN_NOT
    )
    # The ASR transcript of the processed audio (for the quality grade + editor).
    transcript = models.TextField(blank=True, default="")
    # Quality grade comparing the transcript to the intended text:
    # {score, should_regenerate, reason, method}. See narration.grade_transcription.
    grade = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created_on"]

    def __str__(self):
        return f"variant {self.pk} of segment#{self.segment_id}"
