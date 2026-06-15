"""Django settings for the inference.club backend.

Defaults preserve local-dev behavior (SQLite, debug on, permissive CORS for the
Nuxt dev server). Production overrides everything via env vars; in containerized
deploys these come from the .env file rendered by Pulumi.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


# ---- core ---------------------------------------------------------------

# A real SECRET_KEY must be supplied in production. The fallback is fine for
# dev only and matches the historical insecure key so existing sessions keep
# working.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-cjs=#69#qf)qbhx#b!__pty1pl#twocrl&h)g98e_$))lt1+$+",
)

DEBUG = _env_bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", default=["*"])

# ---- CORS / CSRF --------------------------------------------------------

# Frontend origins allowed to make credentialed requests. Override in prod with
# a comma-separated list, e.g. "https://inference.club,https://www.inference.club".
_DEV_FRONTEND_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]
CORS_ALLOWED_ORIGINS = _env_list("DJANGO_CORS_ALLOWED_ORIGINS", _DEV_FRONTEND_ORIGINS)
CSRF_TRUSTED_ORIGINS = _env_list("DJANGO_CSRF_TRUSTED_ORIGINS", _DEV_FRONTEND_ORIGINS)

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False
CSRF_USE_SESSIONS = False

# When the frontend and API live on different subdomains of the same parent
# (inference.club + api.inference.club), the CSRF cookie has to be set on the
# parent so the frontend's JavaScript can read it via document.cookie. Same
# story for the session cookie. In dev (localhost) we leave these unset so
# Django defaults to the request host.
CSRF_COOKIE_DOMAIN = os.environ.get("DJANGO_CSRF_COOKIE_DOMAIN") or None
SESSION_COOKIE_DOMAIN = os.environ.get("DJANGO_SESSION_COOKIE_DOMAIN") or None

# ---- Tailscale (for reaching agents over the inference.club tailnet) -----

# Tailnet name (the part before .ts.net), used when constructing FQDNs for
# agent reachability and when minting auth keys via OAuth. "-" is Tailscale's
# placeholder for "the API token's default tailnet".
TAILSCALE_TAILNET = os.environ.get("TAILSCALE_TAILNET", "")

# Production: OAuth client mints fresh per-agent ephemeral keys. Bootstrap:
# fall back to a single static reusable key so we don't need OAuth set up to
# iterate.
TAILSCALE_OAUTH_CLIENT_ID = os.environ.get("TAILSCALE_OAUTH_CLIENT_ID", "")
TAILSCALE_OAUTH_CLIENT_SECRET = os.environ.get("TAILSCALE_OAUTH_CLIENT_SECRET", "")
TAILSCALE_HOST_TAG = os.environ.get("TAILSCALE_HOST_TAG", "tag:club-host")
TAILSCALE_STATIC_AUTHKEY = os.environ.get("TAILSCALE_STATIC_AUTHKEY", "")

# When set (e.g. socks5h://tailscale:1055), tailnet-bound HTTP requests are
# routed through this proxy. Empty in local dev (where the backend talks to
# agents directly).
TAILNET_PROXY_URL = os.environ.get("TAILNET_PROXY_URL", "")

# Local-dev (no-Tailscale) mode. When True, the agent register endpoint trusts
# the address the agent reports (host:port) and skips both the club-host-<id>
# hostname rewrite and Tailscale key minting — the agent runs with AGENT_DIRECT
# and the backend reaches it directly (e.g. host.docker.internal:<port>).
# MUST stay False in production, where agents are only reachable over the
# tailnet by their canonical club-host-<id> hostname.
INFERENCE_DIRECT_AGENTS = _env_bool("INFERENCE_DIRECT_AGENTS", default=False)

# ---- apps / middleware --------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.accounts",
    "apps.inference",
    "rest_framework",
    "rest_framework.authtoken",
    "social_django",
    "corsheaders",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves collected static files in production. It's a no-op in
    # dev when DEBUG=True since runserver still serves staticfiles directly.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Logs out sessions whose stored epoch no longer matches the user's —
    # how passcode/guest revocation kills live sessions instantly.
    "apps.accounts.middleware.SessionEpochMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
]

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"

# ---- database -----------------------------------------------------------

# DATABASE_URL takes precedence; falls back to local SQLite for dev.
_default_db_url = f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL", _default_db_url),
        conn_max_age=600,
    )
}

# ---- auth ---------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTH_USER_MODEL = "accounts.CustomUser"

REST_FRAMEWORK = {
    # Bearer first so unauthenticated API calls get a proper 401 with a
    # `WWW-Authenticate: Bearer` header (DRF derives the 401-vs-403 decision
    # from the FIRST authenticator; SessionAuthentication returns no auth
    # header, which downgrades 401→403 and confuses OpenAI-style clients).
    # Session still authenticates cookie-based dashboard requests (and keeps
    # enforcing CSRF) since it's tried next.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.BearerTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Per-user rate limits for the OpenAI-compatible proxy (applied via
    # ScopedRateThrottle on the /v1 views; keyed by user since those require a
    # token). Override per-environment with the env vars below.
    # NOTE: throttling uses Django's cache; with multiple worker processes and
    # the default in-process cache the limit is enforced per-worker. Point
    # CACHES at a shared backend (e.g. Redis) for exact global limits.
    "DEFAULT_THROTTLE_RATES": {
        "inference": os.environ.get("INFERENCE_RATE_LIMIT", "60/min"),
        "models": os.environ.get("MODELS_RATE_LIMIT", "120/min"),
        # Fallbacks for guest/passcode accounts; the live values come from
        # the admin-editable AccessPolicy (these apply if it's unreadable).
        "inference_anon": os.environ.get("ANON_INFERENCE_RATE_LIMIT", "15/min"),
        "models_anon": os.environ.get("ANON_MODELS_RATE_LIMIT", "60/min"),
    },
}

# ---- inference proxy guardrails -----------------------------------------
# Bounds on a single inference request, to protect providers' hardware from
# oversized or runaway jobs. See apps.inference.openai_views.
INFERENCE_MAX_MESSAGES = int(os.environ.get("INFERENCE_MAX_MESSAGES", "200"))
INFERENCE_MAX_INPUT_CHARS = int(os.environ.get("INFERENCE_MAX_INPUT_CHARS", "100000"))
INFERENCE_MAX_OUTPUT_TOKENS = int(os.environ.get("INFERENCE_MAX_OUTPUT_TOKENS", "8192"))

# ---- cache --------------------------------------------------------------
# Backs DRF throttling and the rate-limit usage meter. A SHARED backend
# (Redis) is required for accurate limits + meter across multiple gunicorn
# workers; without REDIS_URL we fall back to a per-process cache, which is
# fine for a single worker / local poking but enforces limits per-worker.
_REDIS_URL = os.environ.get("REDIS_URL", "")
if _REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

# ---- Celery (async jobs & workflows, PRD 10) ----------------------------
# Celery is the execution engine for queued jobs; Postgres is the source of
# truth. Broker + result backend default to REDIS_URL (a separate logical DB
# so the queue never collides with the cache). Async is OPT-IN and degrades
# safely: with no broker, ASYNC_ENABLED is False and the API rejects async
# submissions with a 503 — synchronous inference is unaffected either way.
def _redis_db(url: str, db: int) -> str:
    """Point a redis:// URL at a specific logical DB index (keeps the broker,
    results, and cache from stepping on each other when one server is shared)."""
    if not url:
        return ""
    base, _, _ = url.partition("?")
    base = base.rstrip("/")
    # Strip an existing trailing "/<n>" db selector, then append ours.
    head, sep, tail = base.rpartition("/")
    if sep and tail.isdigit():
        base = head
    return f"{base}/{db}"


CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "") or _redis_db(_REDIS_URL, 1)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "") or _redis_db(
    _REDIS_URL, 2
)
# Master switch the API/dispatcher read. True only when a broker exists, unless
# explicitly forced (e.g. CELERY_TASK_ALWAYS_EAGER in tests).
ASYNC_ENABLED = _env_bool("ASYNC_ENABLED", default=bool(CELERY_BROKER_URL))
CELERY_TASK_ALWAYS_EAGER = _env_bool("CELERY_TASK_ALWAYS_EAGER", default=False)
if CELERY_TASK_ALWAYS_EAGER:
    ASYNC_ENABLED = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # one heavy job at a time per worker slot
CELERY_TASK_TRACK_STARTED = True
CELERY_TIMEZONE = "UTC"
CELERY_RESULT_EXPIRES = 3600

# How often the dispatcher tick claims queued jobs and advances workflow runs.
JOB_DISPATCH_INTERVAL_SECONDS = float(
    os.environ.get("JOB_DISPATCH_INTERVAL_SECONDS", "2.0")
)
# A job that can't find an online provider stays QUEUED this long before it's
# failed as "no capacity ever showed up" (bounds a job waiting forever).
JOB_NO_PROVIDER_TIMEOUT_SECONDS = int(
    os.environ.get("JOB_NO_PROVIDER_TIMEOUT_SECONDS", str(60 * 60))
)
# A job stuck PROCESSING past this (worker died mid-run) is reclaimed by the
# reaper and retried. Comfortably above the per-call upstream timeout (300s).
JOB_RUNNING_TIMEOUT_SECONDS = int(
    os.environ.get("JOB_RUNNING_TIMEOUT_SECONDS", str(20 * 60))
)
# Max items a workflow `map` step may fan out to (bounds runaway fan-out).
WORKFLOW_MAX_FANOUT = int(os.environ.get("WORKFLOW_MAX_FANOUT", "64"))
# How many `compose`/RENDER jobs may run at once on the central worker (PRD 12
# §5.5). FFmpeg is CPU/encode-heavy, so this is deliberately small.
RENDER_MAX_CONCURRENT = int(os.environ.get("RENDER_MAX_CONCURRENT", "1"))

CELERY_BEAT_SCHEDULE = {}
if ASYNC_ENABLED:
    CELERY_BEAT_SCHEDULE["dispatch-queued-jobs"] = {
        "task": "apps.inference.tasks.dispatch_queued",
        "schedule": JOB_DISPATCH_INTERVAL_SECONDS,
    }
    CELERY_BEAT_SCHEDULE["reap-stuck-jobs"] = {
        "task": "apps.inference.tasks.reap_stuck_jobs",
        "schedule": 60.0,
    }

AUTHENTICATION_BACKENDS = (
    "social_core.backends.github.GithubOAuth2",
    "django.contrib.auth.backends.ModelBackend",
)

# ---- social auth (GitHub OAuth) -----------------------------------------

# Register an OAuth App at https://github.com/settings/developers.
# Callback URL must be: <SCHEME>://<HOST>/oauth/complete/github/
SOCIAL_AUTH_GITHUB_KEY = os.environ.get("GITHUB_OAUTH_CLIENT_ID", "")
SOCIAL_AUTH_GITHUB_SECRET = os.environ.get("GITHUB_OAUTH_CLIENT_SECRET", "")
SOCIAL_AUTH_GITHUB_SCOPE = ["user:email"]

# CustomUser uses email as USERNAME_FIELD with no username column.
SOCIAL_AUTH_USER_FIELDS = ["email"]

# Default pipeline + two custom steps: upgrading a logged-in guest/passcode
# account that links GitHub ("Keep this account"), and keeping `handle` in
# sync with the GitHub login for non-aliased users. See apps/accounts/pipeline.py.
SOCIAL_AUTH_PIPELINE = (
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    "social_core.pipeline.social_auth.auth_allowed",
    "social_core.pipeline.social_auth.social_user",
    "social_core.pipeline.user.get_username",
    "social_core.pipeline.user.create_user",
    "social_core.pipeline.social_auth.associate_user",
    "social_core.pipeline.social_auth.load_extra_data",
    "social_core.pipeline.user.user_details",
    "apps.accounts.pipeline.finalize_anonymous_upgrade",
    "apps.accounts.pipeline.set_handle_from_github",
)

# Where to send the browser after the OAuth handshake. Defaults match local dev.
SOCIAL_AUTH_LOGIN_REDIRECT_URL = os.environ.get(
    "SOCIAL_AUTH_LOGIN_REDIRECT_URL", "http://localhost:3001/"
)
SOCIAL_AUTH_LOGIN_ERROR_URL = os.environ.get(
    "SOCIAL_AUTH_LOGIN_ERROR_URL", "http://localhost:3001/login?oauth_error=1"
)

# ---- i18n / static ------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---- object storage (media: generated images/audio/video/3D, STT input) --
#
# Media backend precedence:
#   1. GCS_* env vars        -> Google Cloud Storage, split across a public
#      bucket (generated output, served to browsers straight from
#      storage.googleapis.com) and a private bucket (owner-gated STT input
#      audio). See backend/storage.py. Production.
#   2. OBJECT_STORAGE_* vars -> S3-compatible backend (MinIO in the local
#      compose stack); everything streams through the app's asset route.
#   3. neither               -> local filesystem, so a contributor without
#      MinIO still runs.
# Static files always stay on WhiteNoise.
GCS_PUBLIC_BUCKET = os.environ.get("GCS_PUBLIC_BUCKET", "")
GCS_PRIVATE_BUCKET = os.environ.get("GCS_PRIVATE_BUCKET", "")
GCS_CREDENTIALS_B64 = os.environ.get("GCS_CREDENTIALS_B64", "")

OBJECT_STORAGE_BUCKET = os.environ.get("OBJECT_STORAGE_BUCKET", "")
OBJECT_STORAGE_ENDPOINT = os.environ.get("OBJECT_STORAGE_ENDPOINT", "")
OBJECT_STORAGE_ACCESS_KEY = os.environ.get("OBJECT_STORAGE_ACCESS_KEY", "")
OBJECT_STORAGE_SECRET_KEY = os.environ.get("OBJECT_STORAGE_SECRET_KEY", "")
OBJECT_STORAGE_REGION = os.environ.get("OBJECT_STORAGE_REGION", "us-east-1")

# When media lives on GCS, public asset kinds get direct public-bucket URLs
# in API responses and the asset route 302s to them; otherwise (MinIO/FS,
# neither browser-reachable) the app streams the bytes itself.
MEDIA_DIRECT_PUBLIC_URLS = bool(GCS_PUBLIC_BUCKET and GCS_PRIVATE_BUCKET)

if MEDIA_DIRECT_PUBLIC_URLS:
    _default_storage = {"BACKEND": "backend.storage.KindRoutedGCSStorage"}
elif OBJECT_STORAGE_BUCKET:
    _default_storage = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": OBJECT_STORAGE_BUCKET,
            "region_name": OBJECT_STORAGE_REGION,
            # Path-style addressing — required for MinIO (no per-bucket DNS).
            "addressing_style": "path",
            # Media is served through our own authenticated route, not via
            # public bucket ACLs, so keep objects private.
            "default_acl": None,
            "querystring_auth": True,
            "file_overwrite": False,
        },
    }
    if OBJECT_STORAGE_ENDPOINT:
        _default_storage["OPTIONS"]["endpoint_url"] = OBJECT_STORAGE_ENDPOINT
    if OBJECT_STORAGE_ACCESS_KEY:
        _default_storage["OPTIONS"]["access_key"] = OBJECT_STORAGE_ACCESS_KEY
        _default_storage["OPTIONS"]["secret_key"] = OBJECT_STORAGE_SECRET_KEY
else:
    _default_storage = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

# Cache-busted, gzip/brotli-compressed static asset storage for WhiteNoise.
STORAGES = {
    "default": _default_storage,
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ---- speech-to-text (STT) guardrails ------------------------------------
# Bound uploaded audio so a single request can't exhaust a worker's memory or
# a provider's GPU. 25 MB matches OpenAI's transcription limit.
STT_MAX_UPLOAD_BYTES = int(os.environ.get("STT_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
STT_ALLOWED_CONTENT_TYPES = {
    "audio/wav", "audio/x-wav", "audio/wave",
    "audio/mpeg", "audio/mp3", "audio/mp4", "audio/m4a", "audio/x-m4a",
    "audio/flac", "audio/x-flac", "audio/ogg", "audio/webm",
    "video/mp4", "video/webm",  # webm/mp4 often carry an audio-only track
    "application/octet-stream",  # some clients send this for files
}
# Persist the uploaded audio (as an INPUT_AUDIO MediaAsset) so the playground
# and profile can replay it. Set False to transcribe-and-discard.
STT_STORE_INPUT_AUDIO = _env_bool("STT_STORE_INPUT_AUDIO", default=True)

# ---- image generation guardrails ----------------------------------------
IMAGE_MAX_PROMPT_CHARS = int(os.environ.get("IMAGE_MAX_PROMPT_CHARS", "4000"))
IMAGE_MAX_N = int(os.environ.get("IMAGE_MAX_N", "4"))
# Source image (and mask) upload cap for /v1/images/edits.
IMAGE_MAX_UPLOAD_BYTES = int(os.environ.get("IMAGE_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
IMAGE_ALLOWED_CONTENT_TYPES = {
    "image/png", "image/jpeg", "image/jpg", "image/webp",
    "application/octet-stream",
}

# ---- text-to-speech (TTS) guardrails ------------------------------------
TTS_MAX_INPUT_CHARS = int(os.environ.get("TTS_MAX_INPUT_CHARS", "5000"))
# Default voice + language when the client omits them. The Riva/Magpie NIM
# serves these; override per-deployment if your model uses different names.
TTS_DEFAULT_VOICE = os.environ.get("TTS_DEFAULT_VOICE", "Magpie-Multilingual.EN-US.Mia")
TTS_DEFAULT_LANGUAGE = os.environ.get("TTS_DEFAULT_LANGUAGE", "en-US")
TTS_DEFAULT_SAMPLE_RATE = int(os.environ.get("TTS_DEFAULT_SAMPLE_RATE", "44100"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- proxy/headers ------------------------------------------------------

# When running behind Caddy / nginx, trust the X-Forwarded-Proto header so
# Django generates correct https:// absolute URLs (matters for OAuth callbacks).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
