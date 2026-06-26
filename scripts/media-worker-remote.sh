#!/usr/bin/env bash
# media-worker-remote.sh — offload encoding to this (beefier) machine over SSH/WireGuard.
#
# Reuses the SAME pipeline as the Pi: it claims the inbox batches on the Pi (moves them
# to work/ so the Pi's own overnight timer won't also grab them), rsyncs a local MIRROR
# of just what's needed (inbox batches + tracks/ for geotag + existing sidecars for
# dedup), runs `media-ingest.sh --once` locally, then rsyncs the encoded library +
# sidecars back up and triggers a reindex on the Pi. Deterministic, so a dropped link
# just leaves the batch claimed in work/ to be reclaimed (`media-ingest.sh --reclaim`).
#
# Needs ffmpeg + exiftool + ImageMagick locally. Reads PI_HOST/PI_USER[/PI_PASSWORD] or
# PI_SSH from the repo-root .env (mirrors deploy-sally-api.sh). Optional SSH_KEY.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/sally-helpers.sh
. "$HERE/lib/sally-helpers.sh"
REPO="$(cd "$HERE/.." && pwd)"
[ -f "$REPO/.env" ] && { set -a; . "$REPO/.env"; set +a; }

: "${REMOTE_HOME:=/mnt/usb/home}"          # MEDIA_HOME on the Pi
: "${REMOTE_CATALOG:=/var/lib/sally/catalog.json}"
: "${REMOTE_MEDIA_DIR:=/opt/sally/media}"  # where deploy-media-worker.sh put the scripts
: "${MIRROR:=${TMPDIR:-/tmp}/sally-media-mirror}"

require_cmd rsync ffmpeg exiftool

# Build the ssh/rsync transport (key or sshpass), matching deploy-sally-api.sh style.
PI_SSH="${PI_SSH:-${PI_USER:-pi}@${PI_HOST:?set PI_HOST or PI_SSH in .env}}"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
[ -n "${SSH_KEY:-}" ] && SSH_OPTS+=(-i "$SSH_KEY")
if [ -n "${PI_PASSWORD:-}" ] && command -v sshpass >/dev/null 2>&1; then
  export SSHPASS="$PI_PASSWORD"; SSH=(sshpass -e ssh "${SSH_OPTS[@]}"); RSH="sshpass -e ssh ${SSH_OPTS[*]}"
else
  SSH=(ssh "${SSH_OPTS[@]}"); RSH="ssh ${SSH_OPTS[*]}"
fi
rsync_() { if [ -n "${PI_PASSWORD:-}" ] && command -v sshpass >/dev/null 2>&1; then sshpass -e rsync -e "ssh ${SSH_OPTS[*]}" "$@"; else rsync -e "ssh ${SSH_OPTS[*]}" "$@"; fi; }

header "claiming inbox batches on $PI_SSH"
CLAIMED="$("${SSH[@]}" "$PI_SSH" "mkdir -p '$REMOTE_HOME/work'; \
  for b in '$REMOTE_HOME/inbox'/*/; do [ -d \"\$b\" ] || continue; \
    id=\$(basename \"\$b\"); mv \"\$b\" '$REMOTE_HOME/work/\$id' 2>/dev/null && echo \"\$id\"; done")"
[ -n "$CLAIMED" ] || { ok "nothing to claim — inbox empty"; exit 0; }
echo "$CLAIMED" | sed 's/^/  claimed /'

header "mirroring down to $MIRROR"
mkdir -p "$MIRROR/work" "$MIRROR/tracks" "$MIRROR/catalog/items"
rsync_ -az --delete "$PI_SSH:$REMOTE_HOME/work/"          "$MIRROR/work/"
rsync_ -az          "$PI_SSH:$REMOTE_HOME/tracks/"        "$MIRROR/tracks/" 2>/dev/null || true
rsync_ -az          "$PI_SSH:$REMOTE_HOME/catalog/items/" "$MIRROR/catalog/items/" 2>/dev/null || true

header "encoding locally"
# Point the worker entirely at the mirror; process each claimed batch.
export MEDIA_HOME="$MIRROR" INBOX_DIR="$MIRROR/inbox" WORK_DIR="$MIRROR/work" \
       MEDIA_ROOT="$MIRROR/library" ORIGINALS_DIR="$MIRROR/originals" \
       SIDECAR_DIR="$MIRROR/catalog/items" TRACKS_DIR="$MIRROR/tracks" \
       FAILED_DIR="$MIRROR/failed" LOGS_DIR="$MIRROR/logs" \
       CATALOG_JSON="$MIRROR/catalog.json" KEEP_ORIGINALS=0
for id in $CLAIMED; do
  [ -d "$MIRROR/work/$id" ] && "$HERE/media-ingest.sh" --batch "$MIRROR/work/$id"
done

header "publishing back to $PI_SSH"
rsync_ -az "$MIRROR/library/"        "$PI_SSH:$REMOTE_HOME/library/"
rsync_ -az "$MIRROR/catalog/items/"  "$PI_SSH:$REMOTE_HOME/catalog/items/"
"${SSH[@]}" "$PI_SSH" "SIDECAR_DIR='$REMOTE_HOME/catalog/items' MEDIA_ROOT='$REMOTE_HOME/library' \
  CATALOG_JSON='$REMOTE_CATALOG' python3 '$REMOTE_MEDIA_DIR/media-reindex.py'"
ok "offload complete"
