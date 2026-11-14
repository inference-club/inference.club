#!/usr/bin/env bash
# Install the inference.club agent skill (+ the `inference-club` CLI).
#
#   integrations/skills/install.sh                    # Claude Code (~/.claude/skills)
#   integrations/skills/install.sh --hermes           # Hermes default profile
#   integrations/skills/install.sh --hermes minimal   # a Hermes profile
#   integrations/skills/install.sh --dir PATH         # any skills directory
#
# The skill is copied (not symlinked) so the agent's sandbox can read it. The CLI
# is linked to ~/.local/bin/inference-club. Set INFERENCE_CLUB_API_KEY in the
# agent's environment (Hermes: the profile's .env).
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/inference-club"
target=""
case "${1:-}" in
  --hermes)
    if [ -n "${2:-}" ]; then target="$HOME/.hermes/profiles/$2/skills/media/inference-club"
    else target="$HOME/.hermes/skills/media/inference-club"; fi ;;
  --dir) target="${2:?--dir needs a path}/inference-club" ;;
  ""|--claude) target="$HOME/.claude/skills/inference-club" ;;
  *) echo "unknown option: $1" >&2; exit 2 ;;
esac

mkdir -p "$(dirname "$target")"
rm -rf "$target"
cp -R "$SRC" "$target"
chmod +x "$target/scripts/ic.py"
echo "installed skill → $target"

mkdir -p "$HOME/.local/bin"
ln -sf "$target/scripts/ic.py" "$HOME/.local/bin/inference-club"
echo "linked CLI     → $HOME/.local/bin/inference-club"

if [ -z "${INFERENCE_CLUB_API_KEY:-}" ]; then
  echo "note: set INFERENCE_CLUB_API_KEY (Dashboard → Settings → Token) in the agent's environment."
fi
