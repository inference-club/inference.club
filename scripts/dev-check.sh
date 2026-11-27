#!/usr/bin/env bash
# Readiness check for local development against the home cluster.
#
#   scripts/dev-check.sh            # stack + agent + catalog (seconds)
#   scripts/dev-check.sh --up       # start what is down first, then check
#   scripts/dev-check.sh --smoke    # also make one real request per service
#
# The stack is the root docker-compose.yml (backend :8101, frontend
# :${FRONTEND_PORT:-3101}). Inference comes from the in-cluster `agent-dev`
# Deployment, which discovers labelled Services in the `inference-club`
# namespace and registers them with this backend. It is usually parked at 0
# replicas; --up scales it to 1.
#
# Exit status is the number of failed checks, so it can gate other scripts.
set -u
cd "$(dirname "$0")/.."

API="http://localhost:8101"
WEB="http://localhost:${FRONTEND_PORT:-3101}"
NS="inference-club"
IC="python3 integrations/skills/inference-club/scripts/ic.py"
UP=0 SMOKE=0
for a in "$@"; do
  case "$a" in
    --up) UP=1 ;;
    --smoke) SMOKE=1 ;;
    *) echo "unknown flag $a" >&2; exit 64 ;;
  esac
done

fails=0
ok()   { printf '  \033[32mok\033[0m    %s\n' "$*"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$*"; fails=$((fails + 1)); }
note() { printf '  \033[33mnote\033[0m  %s\n' "$*"; }
code() { curl -s -o /dev/null -m "${2:-10}" -w '%{http_code}' "$1"; }

if [ "$UP" = 1 ]; then
  echo "Starting"
  docker compose up -d >/dev/null 2>&1 && ok "docker compose up -d" || bad "docker compose up -d"
  kubectl -n "$NS" scale deploy/agent-dev --replicas=1 >/dev/null 2>&1 \
    && kubectl -n "$NS" rollout status deploy/agent-dev --timeout=120s >/dev/null 2>&1 \
    && ok "agent-dev scaled to 1" || bad "agent-dev did not come up"
  for _ in $(seq 1 60); do [ "$(code "$API/healthz" 3)" = 200 ] && break; sleep 2; done
  for _ in $(seq 1 60); do [ "$(code "$WEB/" 30)" = 200 ] && break; sleep 3; done
fi

echo "Stack"
for svc in postgres redis backend frontend celery-worker celery-beat prober; do
  state=$(docker compose ps --format '{{.State}}' "$svc" 2>/dev/null | head -1)
  [ "$state" = running ] && ok "compose/$svc" || bad "compose/$svc is ${state:-not created}"
done
[ "$(code "$API/readyz")" = 200 ] && ok "backend $API/readyz" || bad "backend $API/readyz"
[ "$(code "$WEB/" 60)" = 200 ] && ok "frontend $WEB" || bad "frontend $WEB"

echo "Agent"
ready=$(kubectl -n "$NS" get deploy agent-dev -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
if [ "${ready:-0}" -ge 1 ]; then
  ok "agent-dev pod ready"
  want=$(kubectl -n "$NS" get deploy agent-club-lan -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null)
  have=$(kubectl -n "$NS" get deploy agent-dev -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null)
  [ -z "$want" ] || [ "$want" = "$have" ] || note "agent-dev runs ${have##*:}, agent-club-lan runs ${want##*:}"
  target=$(kubectl -n "$NS" get deploy agent-dev -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="INFERENCE_CLUB_URL")].value}' 2>/dev/null)
  lan=$(ipconfig getifaddr en0 2>/dev/null || true)
  case "$target" in
    *"$lan"*) ok "agent registers to this machine" ;;
    *) bad "agent registers to $target but this machine is ${lan:-off the LAN}" ;;
  esac
else
  bad "agent-dev has no ready pod (scripts/dev-check.sh --up)"
fi

# The dev superuser's API token, read from the running backend. Never printed.
KEY=$(docker compose exec -T backend python manage.py shell -c "
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
u = get_user_model().objects.filter(is_superuser=True).order_by('id').first()
print('KEY=' + Token.objects.get_or_create(user=u)[0].key)" 2>/dev/null | sed -n 's/^KEY=//p')
if [ -z "$KEY" ]; then
  bad "could not read a dev API token from the backend"
  echo; echo "$fails failed"; exit "$fails"
fi
export INFERENCE_CLUB_API_KEY="$KEY" INFERENCE_CLUB_BASE_URL="$API"

echo "Catalog"
models=$(curl -s -m 15 -H "Authorization: Bearer $KEY" "$API/v1/models")
local_n=$(printf '%s' "$models" | python3 -c "
import json, sys
d = json.load(sys.stdin).get('data', [])
mine = [m for m in d if not m.get('provider')]
for m in mine: print('       %-14s %s' % (m.get('service_type'), m['id']), file=sys.stderr)
print(len(mine))" 2>/tmp/dev-check-models.$$ || echo 0)
[ "${local_n:-0}" -gt 0 ] && ok "$local_n cluster models in /v1/models" || bad "no cluster models in /v1/models"
cat /tmp/dev-check-models.$$ 2>/dev/null; rm -f /tmp/dev-check-models.$$

if [ "$SMOKE" = 1 ]; then
  echo "Smoke (one real request per service)"
  tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
  try() { # try <label> <command...>
    label=$1; shift; start=$(date +%s)
    if out=$("$@" 2>/dev/null) && printf '%s' "$out" | grep -q '"ok": true'; then
      ok "$label ($(( $(date +%s) - start ))s)"
    else
      bad "$label: $(printf '%s' "$out" | tr -d '\n' | sed -n 's/.*"error": "\([^"]\{0,140\}\).*/\1/p')"
    fi
  }
  ids() { printf '%s' "$models" | python3 -c "
import json, sys
for m in json.load(sys.stdin).get('data', []):
    if not m.get('provider') and m.get('service_type') == '$1': print(m['id'])"; }
  for m in $(ids llm);   do try "llm    $m" $IC chat "Reply with exactly: pong" --model "$m" --timeout 120; done
  for m in $(ids image); do try "image  $m" $IC image "a red toy jack on a white table" --model "$m" -o "$tmp/i.png" --timeout 240; done
  for m in $(ids tts);   do try "tts    $m" $IC speech "[S1] Hello from the smoke test." --model "$m" -o "$tmp/$(echo "$m" | tr '/' '_').wav" --timeout 300; done
  wav=$(ls "$tmp"/*.wav 2>/dev/null | head -1)
  [ -n "$wav" ] && for m in $(ids stt); do try "stt    $m" $IC transcribe "$wav" --model "$m"; done
  for m in $(ids music);  do try "music  $m" $IC music "mellow lofi piano, instrumental" --duration 20 --model "$m" -o "$tmp/s.mp3" --timeout 300; done
  for m in $(ids scrape); do try "scrape $m" $IC scrape https://example.com --timeout 120; done
  if [ -n "$wav" ]; then
    for m in $(ids audio-enhance); do
      c=$(curl -s -o /dev/null -m 180 -w '%{http_code}' -X POST "$API/v1/audio/enhance" \
        -H "Authorization: Bearer $KEY" -F "file=@$wav" -F "model=$m")
      [ "$c" = 200 ] && ok "enhance $m" || bad "enhance $m: HTTP $c"
    done
  fi
  # Video is minutes per clip, so only check that the service answers.
  for m in $(ids video); do
    avail=$(curl -s -m 15 -H "Authorization: Bearer $KEY" "$API/v1/capacity" | python3 -c "
import json, sys
print(any(r['model'] == '$m' and r.get('available') for r in json.load(sys.stdin).get('data', [])))")
    note "video  $m not exercised (slow); capacity says available=$avail"
  done
fi

echo
[ "$fails" = 0 ] && echo "All checks passed. Open $WEB" || echo "$fails failed"
exit "$fails"
