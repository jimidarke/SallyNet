#!/usr/bin/env bash
# media-ingest.sh — the SallyNet home-media ingest worker.
#
# Filesystem-as-queue, no broker. A "job" is one directory under inbox/. A worker
# CLAIMS a batch by `mv inbox/<id> work/<id>` (atomic on one filesystem, so the Pi and
# a laptop worker can't double-grab it). Each media file is hashed (sha256) for
# idempotent dedup, metadata+geotag extracted, transcoded to the gold-standard profile,
# given a 480x270 poster, published into library/ with an atomic mv, and described by a
# per-item sidecar JSON. The batch dir is removed on success or moved to failed/ on error.
# Finally catalog.json is rebuilt.
#
# Modes:
#   --once            process every batch currently in inbox, then exit (overnight timer)
#   --watch           process, then block on inotifywait for new batches (live mode)
#   --batch <dir>     process exactly one batch dir (claims it if under inbox/)
#   --reclaim         move stale work/ batches (older than RECLAIM_MIN) back to inbox/
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/sally-helpers.sh
. "$HERE/lib/sally-helpers.sh"
load_conf

# --- paths (conf/env overridable) --------------------------------------------
: "${MEDIA_HOME:=/mnt/usb/home}"
: "${INBOX_DIR:=$MEDIA_HOME/inbox}"
: "${WORK_DIR:=$MEDIA_HOME/work}"
: "${MEDIA_ROOT:=$MEDIA_HOME/library}"
: "${ORIGINALS_DIR:=$MEDIA_HOME/originals}"
: "${SIDECAR_DIR:=$MEDIA_HOME/catalog/items}"
: "${TRACKS_DIR:=$MEDIA_HOME/tracks}"
: "${FAILED_DIR:=$MEDIA_HOME/failed}"
: "${LOGS_DIR:=$MEDIA_HOME/logs}"
: "${CATALOG_JSON:=/var/lib/sally/catalog.json}"
: "${KEEP_ORIGINALS:=1}"
: "${RECLAIM_MIN:=30}"
: "${GEOTAG_WINDOW_SEC:=120}"

VIDEO_EXT="mp4 mov m4v mkv avi 3gp 3g2 webm mts m2ts wmv flv"
PHOTO_EXT="jpg jpeg png heic heif webp tif tiff bmp gif"

require_cmd sha256sum jq python3
mkdir -p "$INBOX_DIR" "$WORK_DIR" "$MEDIA_ROOT" "$SIDECAR_DIR" "$TRACKS_DIR" \
         "$FAILED_DIR" "$LOGS_DIR" "$(dirname "$CATALOG_JSON")"

# --- helpers -----------------------------------------------------------------
ext_lc()   { local e="${1##*.}"; printf '%s' "${e,,}"; }
is_in()    { local n="$1"; shift; for x in $*; do [ "$n" = "$x" ] && return 0; done; return 1; }
slug()     { printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//'; }

# capture-ts slug from an ISO datetime: 2026-07-04T14:22:31-06:00 -> 2026-07-04T14-22-31
cap_slug() { printf '%s' "$1" | sed -E 's/[+-][0-9]{2}:[0-9]{2}$//; s/Z$//; s/:/-/g; s/\..*$//'; }

# Route a file to a collection: claimed trip (upload.json) > drone filename > unsorted.
# Echoes "<cid>\t<kind>\t<title>\t<reldir>".
route_collection() {
  local fname="$1" trip="$2" triptitle="$3" cid kind title reldir
  if [ -n "$trip" ] && [ "$trip" != "unsorted" ] && [ "$trip" != "new" ]; then
    cid="$(slug "$trip")"; kind="trip"; title="${triptitle:-$trip}"; reldir="trips/$cid"
  elif [ -n "$trip" ] && [ "$trip" = "new" ] && [ -n "$triptitle" ]; then
    cid="$(slug "$triptitle")"; kind="trip"; title="$triptitle"; reldir="trips/$cid"
  elif printf '%s' "$fname" | grep -qiE '^(dji_|dji[0-9])|_drone|\.drone\.'; then
    cid="drone"; kind="bucket"; title="Drone"; reldir="drone"
  else
    cid="unsorted"; kind="bucket"; title="Unsorted"; reldir="unsorted"
  fi
  printf '%s\t%s\t%s\t%s' "$cid" "$kind" "$title" "$reldir"
}

# Ensure a trip collection has a trip.json (minimal, human-editable later).
ensure_trip_json() {
  local cid="$1" title="$2" tj="$MEDIA_ROOT/trips/$cid/trip.json"
  [ -f "$tj" ] && return 0
  mkdir -p "$MEDIA_ROOT/trips/$cid"
  jq -n --arg id "$cid" --arg title "$title" \
    '{id:$id, kind:"trip", title:$title}' > "$tj.tmp" && mv "$tj.tmp" "$tj"
}

# sha already ingested? (sidecar carries the source sha256)
already_have() {
  local sha="$1"
  grep -lF "\"$sha\"" "$SIDECAR_DIR"/*.json 2>/dev/null | head -1
}

process_file() {
  local src="$1" trip="$2" triptitle="$3" uploader="$4"
  local fname ext type sha id route cid kind ctitle reldir
  fname="$(basename "$src")"
  ext="$(ext_lc "$fname")"
  if is_in "$ext" "$VIDEO_EXT"; then type="video"
  elif is_in "$ext" "$PHOTO_EXT"; then type="photo"
  else warn "skip unsupported: $fname"; return 0; fi

  sha="$(sha256sum "$src" | cut -d' ' -f1)"
  local dup; dup="$(already_have "$sha" || true)"
  if [ -n "$dup" ]; then ok "dedup skip $fname (already $(basename "$dup" .json))"; return 0; fi
  id="${sha:0:12}"

  # Capture datetime first (drives the on-disk filename + sort order).
  local cap_iso cap
  cap_iso="$(python3 "$HERE/media-extract-meta.py" "$src" \
              --tracks-dir "$TRACKS_DIR" --window-sec "$GEOTAG_WINDOW_SEC" \
              | jq -r '.captureDatetime // empty')"
  cap="$(cap_slug "${cap_iso:-unknown}")"

  route="$(route_collection "$fname" "$trip" "$triptitle")"
  IFS=$'\t' read -r cid kind ctitle reldir <<< "$route"
  [ "$kind" = "trip" ] && ensure_trip_json "$cid" "$ctitle"

  local subdir base relmedia relposter absmedia absposter
  if [ "$type" = "video" ]; then subdir="videos"; base="$cap--$id.mp4"
  else subdir="photos"; base="$cap--$id.jpg"; fi
  relmedia="$reldir/$subdir/$base"
  relposter="$reldir/thumbs/$cap--$id.jpg"
  absmedia="$MEDIA_ROOT/$relmedia"
  absposter="$MEDIA_ROOT/$relposter"
  mkdir -p "$(dirname "$absmedia")" "$(dirname "$absposter")"

  # Transcode to a work-side temp on the same fs as library, then publish atomically.
  # NOTE: process_file runs in a `|| {...}` context, so `set -e` is suppressed here —
  # every fallible step below is checked explicitly so a failed encode can never leave
  # a published sidecar pointing at a missing/empty file.
  # Temp names keep the real extension (a ".part" suffix would hide .mp4/.jpg and
  # break ffmpeg/ImageMagick muxer inference); leading dot keeps them hidden.
  local tmpmedia="$(dirname "$absmedia")/.part-$(basename "$absmedia")"
  local tmpposter="$(dirname "$absposter")/.part-$(basename "$absposter")"
  local enc_rc=0
  if [ "$type" = "video" ]; then
    "$HERE/media-encode-video.sh" "$src" "$tmpmedia" "$tmpposter" || enc_rc=$?
  else
    "$HERE/media-encode-photo.sh" "$src" "$tmpmedia" "$tmpposter" || enc_rc=$?
  fi
  if [ "$enc_rc" -ne 0 ] || [ ! -s "$tmpmedia" ]; then
    fail "encode failed for $fname (rc=$enc_rc)"; rm -f "$tmpmedia" "$tmpposter"; return 1
  fi
  mv -f "$tmpmedia" "$absmedia" || { fail "publish mv failed: $fname"; return 1; }
  [ -f "$tmpposter" ] && mv -f "$tmpposter" "$absposter"

  # Probe the published output for accurate dims/codec/duration.
  local w h codec dur container title
  title="${fname%.*}"
  if [ "$type" = "video" ]; then
    container="mp4"
    w="$(ffprobe -v error -select_streams v:0 -show_entries stream=width  -of default=nk=1:nw=1 "$absmedia" 2>/dev/null | head -1)"
    h="$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of default=nk=1:nw=1 "$absmedia" 2>/dev/null | head -1)"
    codec="$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=nk=1:nw=1 "$absmedia" 2>/dev/null | head -1)"
    dur="$(ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$absmedia" 2>/dev/null | head -1)"
  else
    container="jpg"; codec="jpeg"; dur=""
    if command -v identify >/dev/null 2>&1; then
      w="$(identify -format '%w' "$absmedia" 2>/dev/null)"; h="$(identify -format '%h' "$absmedia" 2>/dev/null)"
    fi
  fi

  # Write the final sidecar (single source of truth) — extraction + injected fields.
  local size; size="$(stat -c '%s' "$absmedia" 2>/dev/null || echo 0)"
  local setargs=(
    --set "id=$id" --set "type=$type" --set "title=$title"
    --set "originalFilename=$fname" --set "sha256=$sha"
    --set "collection.id=$cid" --set "collection.kind=$kind" --set "collection.title=$ctitle"
    --set "mediaPath=$relmedia" --set "posterPath=$relposter"
    --set "codec=$codec" --set "container=$container" --set "fileSizeBytes=$size"
  )
  [ -n "$w" ]   && setargs+=( --set "width=$w" )
  [ -n "$h" ]   && setargs+=( --set "height=$h" )
  [ -n "$dur" ] && setargs+=( --set "durationSec=$dur" )
  [ -n "$uploader" ] && setargs+=( --set "uploader=$uploader" )
  setargs+=( --set "ingestDatetime=$(date -u +%Y-%m-%dT%H:%M:%SZ)" )

  if ! python3 "$HERE/media-extract-meta.py" "$src" \
        --tracks-dir "$TRACKS_DIR" --window-sec "$GEOTAG_WINDOW_SEC" \
        "${setargs[@]}" --out "$SIDECAR_DIR/$id.json"; then
    fail "sidecar write failed for $fname — rolling back"
    rm -f "$absmedia" "$absposter"; return 1
  fi
  ok "published $type $id -> $relmedia"

  # Keep or drop the original.
  if [ "$KEEP_ORIGINALS" = "1" ]; then
    local origdir="$ORIGINALS_DIR/$reldir"
    mkdir -p "$origdir"; cp -f "$src" "$origdir/$base.$ext" 2>/dev/null || true
  fi
}

process_batch() {
  local batch="$1" id wb trip="" triptitle="" uploader=""
  id="$(basename "$batch")"
  # Claim by moving into work/ (atomic on one fs). Already in work? use as-is.
  if [ "$(cd "$(dirname "$batch")" && pwd)" = "$(cd "$WORK_DIR" && pwd)" ]; then
    wb="$batch"
  else
    wb="$WORK_DIR/$id"
    if ! mv "$batch" "$wb" 2>/dev/null; then
      warn "could not claim $id (another worker?)"; return 0
    fi
  fi
  header "batch $id"

  if [ -f "$wb/upload.json" ]; then
    trip="$(jq -r '.trip // empty' "$wb/upload.json" 2>/dev/null || true)"
    triptitle="$(jq -r '.tripTitle // empty' "$wb/upload.json" 2>/dev/null || true)"
    uploader="$(jq -r '.uploader // empty' "$wb/upload.json" 2>/dev/null || true)"
  fi

  local rc=0 f
  while IFS= read -r -d '' f; do
    process_file "$f" "$trip" "$triptitle" "$uploader" || { rc=1; fail "error on $(basename "$f")"; }
  done < <(find "$wb" -type f ! -name 'upload.json' -print0)

  python3 "$HERE/media-reindex.py" || warn "reindex failed"

  if [ "$rc" -eq 0 ]; then
    rm -rf "$wb"; ok "batch $id done"
  else
    mkdir -p "$FAILED_DIR"; echo "ingest errors $(date -u +%FT%TZ)" > "$wb/.err"
    mv "$wb" "$FAILED_DIR/$id" 2>/dev/null || true; fail "batch $id moved to failed/"
  fi
}

run_once() {
  local any=0 b
  for b in "$INBOX_DIR"/*/; do
    [ -d "$b" ] || continue
    any=1; process_batch "${b%/}"
  done
  [ "$any" -eq 1 ] || ok "inbox empty"
}

reclaim() {
  local b age
  for b in "$WORK_DIR"/*/; do
    [ -d "$b" ] || continue
    age=$(( ($(date +%s) - $(stat -c %Y "$b")) / 60 ))
    if [ "$age" -ge "$RECLAIM_MIN" ]; then
      warn "reclaiming stale work batch $(basename "$b") (${age}m) -> inbox"
      mv "${b%/}" "$INBOX_DIR/" 2>/dev/null || true
    fi
  done
}

watch_loop() {
  require_cmd inotifywait
  run_once
  header "watching $INBOX_DIR"
  while true; do
    inotifywait -qq -e create -e moved_to "$INBOX_DIR" || true
    sleep 2  # let a multi-file upload batch settle
    run_once
  done
}

main() {
  local mode="${1:---once}"
  case "$mode" in
    --once)    run_once ;;
    --watch)   watch_loop ;;
    --reclaim) reclaim ;;
    --batch)   [ -n "${2:-}" ] || die "--batch needs a dir"; process_batch "${2%/}" ;;
    -h|--help) sed -n '2,20p' "$0" ;;
    *)         die "unknown mode: $mode (try --once|--watch|--batch <dir>|--reclaim)" ;;
  esac
}

main "$@"
