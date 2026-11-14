DJANGO_SECRET_KEY=__DJANGO_SECRET_KEY__
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=__DOMAIN__,api.__DOMAIN__,localhost
DATABASE_URL=postgres://inference:__POSTGRES_PASSWORD__@postgres:5432/inference
DJANGO_CORS_ALLOWED_ORIGINS=https://__DOMAIN__,https://api.__DOMAIN__
DJANGO_CSRF_TRUSTED_ORIGINS=https://__DOMAIN__,https://api.__DOMAIN__
DJANGO_CSRF_COOKIE_DOMAIN=.__DOMAIN__
DJANGO_SESSION_COOKIE_DOMAIN=.__DOMAIN__
GITHUB_OAUTH_CLIENT_ID=__GITHUB_OAUTH_CLIENT_ID__
GITHUB_OAUTH_CLIENT_SECRET=__GITHUB_OAUTH_CLIENT_SECRET__
SOCIAL_AUTH_LOGIN_REDIRECT_URL=https://__DOMAIN__/
SOCIAL_AUTH_LOGIN_ERROR_URL=https://__DOMAIN__/login?oauth_error=1
PORT=8001
GUNICORN_WORKERS=3

# Tailscale: lets the server reach provider agents over the inference.club
# tailnet. TAILSCALE_TAILNET is the tailnet name (without .ts.net) used to
# build agent FQDNs. Agents get their join key from the backend on register:
#   - OAUTH_CLIENT_ID/SECRET (preferred): the backend mints a fresh one-shot,
#     ephemeral, tagged key per registration. OAuth clients don't expire, and
#     ephemeral devices self-reap, so stale club-host-1-N devices don't pile up.
#   - STATIC_AUTHKEY (fallback): one reusable key handed to every agent.
#     Tailscale auth keys expire after <=90 days, so this silently breaks
#     agent (re)joins once it lapses — which is what took prod down in 2026.
TAILSCALE_TAILNET=__TAILSCALE_TAILNET__
TAILSCALE_OAUTH_CLIENT_ID=__TAILSCALE_OAUTH_CLIENT_ID__
TAILSCALE_OAUTH_CLIENT_SECRET=__TAILSCALE_OAUTH_CLIENT_SECRET__
TAILSCALE_STATIC_AUTHKEY=__TAILSCALE_STATIC_AUTHKEY__
TAILSCALE_HOST_TAG=tag:club-host

# Google Cloud Storage for media. Public asset kinds (generated images/
# audio/video/3D, input images) land in the public bucket and are served to
# browsers straight from storage.googleapis.com; owner-gated input audio
# lands in the private bucket and still streams through the backend's
# authenticated asset route. The credentials are the media-storage service
# account's key JSON, base64-encoded (object access on these buckets only).
GCS_PUBLIC_BUCKET=__GCS_PUBLIC_BUCKET__
GCS_PRIVATE_BUCKET=__GCS_PRIVATE_BUCKET__
GCS_CREDENTIALS_B64=__GCS_CREDENTIALS_B64__
