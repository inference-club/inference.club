#!/usr/bin/env bash
# One-shot migration of media from the VPS-local MinIO bucket to the GCS
# media buckets. Run ON the VPS (as root) after the Pulumi deploy that
# creates the buckets and ships the GCS_* vars into backend.env:
#
#   ssh inference-club 'bash -s' < scripts/migrate-media-to-gcs.sh
#
# Object keys are copied verbatim, so MediaAsset.file names in Postgres keep
# working unchanged. input_audio/ (the only owner-gated kind) goes to the
# private bucket; everything else goes to the public bucket with the same
# immutable Cache-Control the backend sets on new uploads. Idempotent —
# rclone copy skips objects that already match.
set -euo pipefail

ENV_FILE=/srv/inference-club/backend.env
get() { grep "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2-; }

MINIO_SECRET=$(get OBJECT_STORAGE_SECRET_KEY)
MINIO_BUCKET=$(get OBJECT_STORAGE_BUCKET)
GCS_PUBLIC=$(get GCS_PUBLIC_BUCKET)
GCS_PRIVATE=$(get GCS_PRIVATE_BUCKET)

for v in MINIO_SECRET MINIO_BUCKET GCS_PUBLIC GCS_PRIVATE; do
  [ -n "${!v}" ] || { echo "missing $v (is the GCS deploy live?)" >&2; exit 1; }
done

# The media service account key already lives in backend.env (base64 JSON).
SA_KEY=$(mktemp /srv/inference-club/gcs-sa.XXXXXX.json)
trap 'rm -f "$SA_KEY"' EXIT
get GCS_CREDENTIALS_B64 | base64 -d > "$SA_KEY"
chmod 600 "$SA_KEY"

NETWORK=$(docker network ls --format '{{.Name}}' | grep inference-club | head -1)
[ -n "$NETWORK" ] || { echo "compose network not found" >&2; exit 1; }

rclone() {
  docker run --rm --network "$NETWORK" \
    -v "$SA_KEY":/gcs-sa.json:ro \
    -e RCLONE_CONFIG_MINIO_TYPE=s3 \
    -e RCLONE_CONFIG_MINIO_PROVIDER=Minio \
    -e RCLONE_CONFIG_MINIO_ENDPOINT=http://minio:9000 \
    -e RCLONE_CONFIG_MINIO_ACCESS_KEY_ID=inferenceclub \
    -e RCLONE_CONFIG_MINIO_SECRET_ACCESS_KEY="$MINIO_SECRET" \
    -e RCLONE_CONFIG_GCS_TYPE="google cloud storage" \
    -e RCLONE_CONFIG_GCS_SERVICE_ACCOUNT_FILE=/gcs-sa.json \
    -e RCLONE_CONFIG_GCS_BUCKET_POLICY_ONLY=true \
    rclone/rclone "$@"
}

echo "==> public kinds -> gs://$GCS_PUBLIC"
rclone copy "minio:$MINIO_BUCKET" "gcs:$GCS_PUBLIC" \
  --exclude "input_audio/**" \
  --header-upload "Cache-Control: public, max-age=31536000, immutable" \
  --transfers 8 --stats-one-line --stats 15s -v

echo "==> input_audio/ -> gs://$GCS_PRIVATE"
rclone copy "minio:$MINIO_BUCKET/input_audio" "gcs:$GCS_PRIVATE/input_audio" \
  --transfers 8 --stats-one-line --stats 15s -v

echo "==> verify (one-way, size match)"
rclone check "minio:$MINIO_BUCKET" "gcs:$GCS_PUBLIC" \
  --exclude "input_audio/**" --one-way --size-only
rclone check "minio:$MINIO_BUCKET/input_audio" "gcs:$GCS_PRIVATE/input_audio" \
  --one-way --size-only || echo "(no input_audio objects is fine)"

echo "==> done. MinIO left untouched as a fallback; remove it after cutover."
