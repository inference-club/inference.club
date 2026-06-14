# Production stack on the Hetzner VPS. Rendered by Pulumi from
# infra/deployment.ts with image SHAs and env values from stack config.
# Bind mounts under /srv/inference-club/ so volumes are inspectable and easy
# to back up.
services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /srv/inference-club/Caddyfile:/etc/caddy/Caddyfile:ro
      - /srv/inference-club/caddy-data:/data
      - /srv/inference-club/caddy-config:/config
    depends_on:
      - frontend
      - backend

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: inference
      POSTGRES_USER: inference
      POSTGRES_PASSWORD: __POSTGRES_PASSWORD__
    volumes:
      - /srv/inference-club/postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U inference -d inference"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Shared cache for DRF rate limiting + the rate-limit usage meter, so limits
  # are enforced globally across the backend's gunicorn workers rather than
  # per-worker. Cache-only — no persistence volume, since a restart simply
  # resets the in-flight rate-limit windows.
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # S3-compatible object storage for media (STT input audio now; TTS/image
  # output later). Internal only — the backend streams assets through its own
  # authenticated route, so MinIO is never exposed through Caddy.
  minio:
    image: minio/minio:latest
    restart: unless-stopped
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: inferenceclub
      MINIO_ROOT_PASSWORD: __MINIO_ROOT_PASSWORD__
    volumes:
      - /srv/inference-club/minio-data:/data

  # One-shot: wait for MinIO, then create the media bucket. Exits 0 once done;
  # `restart: "no"` so it doesn't loop.
  minio-setup:
    image: minio/mc:latest
    restart: "no"
    depends_on:
      - minio
    entrypoint: >
      /bin/sh -c "
      until mc alias set local http://minio:9000 inferenceclub __MINIO_ROOT_PASSWORD__; do echo 'waiting for minio'; sleep 2; done;
      mc mb -p local/inference-club-media || true;
      echo 'minio bucket ready';
      "

  # Tailscale userspace sidecar. Joins the inference.club tailnet as
  # `club-web` and exposes a SOCKS5 proxy on :1055 that the backend uses to
  # reach provider agents over the tailnet.
  tailscale:
    image: tailscale/tailscale:stable
    restart: unless-stopped
    hostname: club-web
    environment:
      TS_AUTHKEY: __TAILSCALE_WEB_AUTHKEY__
      TS_HOSTNAME: club-web
      TS_USERSPACE: "true"
      TS_STATE_DIR: /var/lib/tailscale
      TS_EXTRA_ARGS: "--advertise-tags=tag:club-web"
      # SOCKS5 only — the backend uses socks5h:// to also resolve MagicDNS
      # via the proxy. Setting TS_OUTBOUND_HTTP_PROXY_LISTEN on the same port
      # would collide with this listener.
      TS_SOCKS5_SERVER: ":1055"
    volumes:
      - /srv/inference-club/tailscale-state:/var/lib/tailscale

  backend:
    image: __BACKEND_IMAGE__
    restart: unless-stopped
    env_file:
      - /srv/inference-club/backend.env
    environment:
      # Tells the backend to send tailnet-bound requests through the sidecar's
      # SOCKS5 proxy. Other outbound traffic (e.g. GitHub OAuth callbacks)
      # goes direct, so the site keeps working even before Tailscale is fully
      # configured.
      TAILNET_PROXY_URL: socks5h://tailscale:1055
      # Shared cache for accurate rate limiting + the usage meter.
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      tailscale:
        condition: service_started
      minio:
        condition: service_started

  # Long-running prober. Hits each active provider's /healthz over the
  # tailnet every 30s and bumps Provider.last_seen_at so idle providers
  # don't appear offline between inference requests. Runs from the same
  # backend image with a different command. See
  # backend/apps/inference/management/commands/probe_providers.py.
  prober:
    image: __BACKEND_IMAGE__
    restart: unless-stopped
    command: ["python", "manage.py", "probe_providers"]
    env_file:
      - /srv/inference-club/backend.env
    environment:
      TAILNET_PROXY_URL: socks5h://tailscale:1055
    depends_on:
      postgres:
        condition: service_healthy
      tailscale:
        condition: service_started

  # Async job execution (PRD 10). The worker runs queued jobs (reaching agents
  # over the tailnet via the SOCKS sidecar, exactly like the backend) and beat
  # fires the dispatcher tick. Both reuse the backend image with a different
  # command, so a backend deploy updates them too. Redis is broker + results.
  celery-worker:
    image: __BACKEND_IMAGE__
    restart: unless-stopped
    command: ["celery", "-A", "backend", "worker", "-l", "info", "--concurrency=4"]
    env_file:
      - /srv/inference-club/backend.env
    environment:
      TAILNET_PROXY_URL: socks5h://tailscale:1055
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      tailscale:
        condition: service_started
      minio:
        condition: service_started

  celery-beat:
    image: __BACKEND_IMAGE__
    restart: unless-stopped
    # -s writes the schedule DB to /tmp; the app user can't write the /app cwd.
    command: ["celery", "-A", "backend", "beat", "-l", "info", "-s", "/tmp/celerybeat-schedule"]
    env_file:
      - /srv/inference-club/backend.env
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  frontend:
    image: __FRONTEND_IMAGE__
    restart: unless-stopped
    environment:
      NUXT_PUBLIC_API_BASE: https://api.__DOMAIN__
      NUXT_HOST: 0.0.0.0
      NUXT_PORT: "3000"
    depends_on:
      - backend
