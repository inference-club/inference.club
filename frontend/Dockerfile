# syntax=docker/dockerfile:1.7

# ---- base: shared toolchain for every stage ----
FROM node:20-alpine AS base
WORKDIR /app
RUN corepack enable


# ---- dev: used by docker-compose for local development.
# Source is bind-mounted at /app and node_modules lives on a named volume,
# so this stage intentionally copies nothing — `yarn install` runs at
# container start against the mounted lockfile. ----
FROM base AS dev
# Force chokidar/Vite to poll for file changes — fs events don't always
# propagate reliably across the macOS↔Linux bind mount, so HMR can miss
# edits without this. Costs a bit of idle CPU.
ENV CHOKIDAR_USEPOLLING=true \
    WATCHPACK_POLLING=true \
    NUXT_HOST=0.0.0.0 \
    NUXT_PORT=3000
EXPOSE 3000
CMD ["sh", "-c", "yarn install --frozen-lockfile && yarn dev --host 0.0.0.0 --port 3000"]


# ---- builder: install deps and build the Nuxt app ----
FROM base AS builder
# Copy manifests first so the install layer caches when source changes.
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

COPY . .
RUN yarn build


# ---- runtime: minimal node image serving the Nitro server (default target) ----
FROM node:20-alpine AS runtime

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
