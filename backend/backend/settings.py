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
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "apps.accounts.authentication.BearerTokenAuthentication",
    ],
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
# Cache-busted, gzip/brotli-compressed static asset storage for WhiteNoise.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- proxy/headers ------------------------------------------------------

# When running behind Caddy / nginx, trust the X-Forwarded-Proto header so
# Django generates correct https:// absolute URLs (matters for OAuth callbacks).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
