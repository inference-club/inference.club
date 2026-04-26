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

  backend:
    image: __BACKEND_IMAGE__
    restart: unless-stopped
    env_file:
      - /srv/inference-club/backend.env
    depends_on:
      postgres:
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
