# syntax=docker/dockerfile:1.7

# ---- base: shared toolchain for every stage ----
# Node 22 (LTS) is required by @nuxtjs/i18n's @intlify/* deps (engine ">= 22")
# and matches the host's Node version. Building on node:20 fails install.
FROM node:22-alpine AS base
WORKDIR /app
RUN corepack enable


# ---- dev: used by docker-compose for local development.
# Source is bind-mounted at /app and node_modules lives on a named volume,
# so this stage intentionally copies nothing — `yarn install` runs at
# container start against the mounted lockfile. ----
FROM base AS dev
# File watching uses native fs events (no polling). This relies on Docker
# Desktop's VirtioFS sharing, which propagates macOS→Linux inotify events
# across the bind mount reliably — unlike the old gRPC FUSE, where events were
# dropped and polling was the workaround. Polling forced Vite/chokidar to stat
# the whole tree on a tight loop, pegging a couple of CPU cores at idle and
# making HMR/builds crawl. If you ever fall back to gRPC FUSE and HMR misses
# edits, re-enable polling via the compose env (set the two POLLING vars to a
# non-empty value) rather than here.
ENV NUXT_HOST=0.0.0.0 \
    NUXT_PORT=3000
EXPOSE 3000
CMD ["sh", "-c", "yarn install --frozen-lockfile && yarn dev --host 0.0.0.0 --port 3000"]


# ---- builder: install deps and build the Nuxt app ----
FROM base AS builder
# Copy manifests first so the install layer caches when source changes.
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

COPY . .
# Nuxt's production build peaks past Node's ~2GB default heap (OOM'd CI at
# 1.9GB); the runner has plenty of RAM, so raise the ceiling.
ENV NODE_OPTIONS=--max-old-space-size=4096
RUN yarn build


# ---- runtime: minimal node image serving the Nitro server (default target) ----
FROM node:22-alpine AS runtime

ENV NODE_ENV=production \
    NUXT_HOST=0.0.0.0 \
    NUXT_PORT=3000 \
    PORT=3000

WORKDIR /app

# Only ship the built output; node_modules are bundled by Nitro.
COPY --from=builder /app/.output ./.output

EXPOSE 3000

# NUXT_PUBLIC_API_BASE is read at runtime by Nuxt's runtimeConfig and overrides
# the build-time default in nuxt.config.ts.
CMD ["node", ".output/server/index.mjs"]
