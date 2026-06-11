#!/usr/bin/env bash
# Make the compose dev stack reachable from phones on your WiFi.
#
#   ./scripts/dev-mobile.sh        # detect LAN IP, recreate frontend+backend
#   ./scripts/dev-mobile.sh off    # back to localhost-only
#
# Writes DEV_HOST=<lan-ip> to the root .env (gitignored); docker-compose.yml
# interpolates it into NUXT_PUBLIC_API_BASE and the CORS/CSRF origins.
# Re-run after your Mac's IP changes (DHCP). While DEV_HOST is set, browse
# via http://<lan-ip>:3100 from the Mac too — cookies are scoped per host,
# so mixing localhost (page) with the LAN IP (API) breaks login.
#
# GitHub OAuth only works on localhost (the OAuth app's callback URL); on
# the phone, use password login — e.g. the seeded design user:
#   designbot@inference.club / designbot-pass-1
set -euo pipefail
cd "$(dirname "$0")/.."

touch .env
grep -v '^DEV_HOST=' .env > .env.tmp || true
mv .env.tmp .env

if [ "${1:-}" = "off" ]; then
  echo "DEV_HOST cleared — localhost-only."
  URL="http://localhost:3100"
else
  IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1)
  echo "DEV_HOST=$IP" >> .env
  URL="http://$IP:3100"
fi

# Env-only change: up -d recreates the two affected containers.
docker compose up -d backend frontend prober

echo
echo "==> open on this Mac and on your phone (same WiFi): $URL"
if [ "${1:-}" != "off" ]; then
  echo "==> NOTE: GitHub OAuth login will NOT work while mobile mode is on"
  echo "    (the OAuth app's only callback is localhost). Use password login"
  echo "    (designbot@inference.club / designbot-pass-1), or run:"
  echo "      ./scripts/dev-mobile.sh off"
fi
