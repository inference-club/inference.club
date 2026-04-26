# syntax=docker/dockerfile:1.7

# ---- builder: install deps, build the Nuxt app ----
FROM node:20-alpine AS builder

WORKDIR /app

# Copy manifests first so the install layer caches when source changes.
COPY package.json yarn.lock ./
RUN corepack enable \
    && yarn install --frozen-lockfile

COPY . .
RUN yarn build


# ---- runtime: minimal node image serving the Nitro server ----
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
