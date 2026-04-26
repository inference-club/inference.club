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
    depends_on:
      postgres:
        condition: service_healthy
      tailscale:
        condition: service_started

  frontend:
    image: __FRONTEND_IMAGE__
    restart: unless-stopped
    environment:
      NUXT_PUBLIC_API_BASE: https://api.__DOMAIN__
      NUXT_HOST: 0.0.0.0
      NUXT_PORT: "3000"
    depends_on:
      - backend
