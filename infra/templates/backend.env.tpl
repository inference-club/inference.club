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
# build agent FQDNs; STATIC_AUTHKEY is the bootstrap key handed to every
# registering agent.
TAILSCALE_TAILNET=__TAILSCALE_TAILNET__
TAILSCALE_STATIC_AUTHKEY=__TAILSCALE_STATIC_AUTHKEY__
TAILSCALE_HOST_TAG=tag:club-host

# Object storage (MinIO) for media — legacy fallback during the GCS
# migration. When the GCS_* vars below are set the backend ignores these;
# keep them (and the minio service) until the GCS cutover is verified, then
# remove both.
OBJECT_STORAGE_BUCKET=inference-club-media
OBJECT_STORAGE_ENDPOINT=http://minio:9000
OBJECT_STORAGE_ACCESS_KEY=inferenceclub
OBJECT_STORAGE_SECRET_KEY=__MINIO_ROOT_PASSWORD__
OBJECT_STORAGE_REGION=us-east-1

# Google Cloud Storage for media. Public asset kinds (generated images/
# audio/video/3D, input images) land in the public bucket and are served to
# browsers straight from storage.googleapis.com; owner-gated input audio
# lands in the private bucket and still streams through the backend's
# authenticated asset route. The credentials are the media-storage service
# account's key JSON, base64-encoded (object access on these buckets only).
GCS_PUBLIC_BUCKET=__GCS_PUBLIC_BUCKET__
GCS_PRIVATE_BUCKET=__GCS_PRIVATE_BUCKET__
GCS_CREDENTIALS_B64=__GCS_CREDENTIALS_B64__
