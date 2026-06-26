#!/usr/bin/env bash
# media-encode-photo.sh — normalize a source photo to a Roku-friendly display copy
# (fit within 1920x1080, downscale-only, sRGB, q85, orientation baked in) plus a
# 480x270 thumbnail for the browse grid. Metadata is read into the catalog sidecar
# separately, so the display copies are -strip'd.
#
# Usage:  media-encode-photo.sh <src> <out.jpg> [<thumb.jpg>]
# Handles HEIC/HEIF only where ImageMagick has libheif (route iPhone HEIC through a
# laptop worker; the Pi's Buster build may lack the delegate).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/sally-helpers.sh
. "$HERE/lib/sally-helpers.sh"
load_conf

SRC="${1:?usage: media-encode-photo.sh <src> <out.jpg> [<thumb.jpg>]}"
OUT="${2:?usage: media-encode-photo.sh <src> <out.jpg> [<thumb.jpg>]}"
THUMB="${3:-}"

: "${MEDIA_MAX_W:=1920}"
: "${MEDIA_MAX_H:=1080}"
: "${MEDIA_PHOTO_Q:=85}"
: "${MEDIA_THUMB_Q:=80}"

# ImageMagick 7 ships `magick`; 6 ships `convert`. Prefer magick.
if command -v magick >/dev/null 2>&1; then IM=(magick); else IM=(convert); fi
command -v "${IM[0]}" >/dev/null 2>&1 || die "ImageMagick not found (magick/convert)"

[ -f "$SRC" ] || die "source not found: $SRC"
mkdir -p "$(dirname "$OUT")"

header "encode photo → fit ${MEDIA_MAX_W}x${MEDIA_MAX_H} q${MEDIA_PHOTO_Q}"
"${IM[@]}" "$SRC" -auto-orient -resize "${MEDIA_MAX_W}x${MEDIA_MAX_H}>" \
  -colorspace sRGB -quality "$MEDIA_PHOTO_Q" -strip "$OUT"
ok "wrote $OUT"

if [ -n "$THUMB" ]; then
  mkdir -p "$(dirname "$THUMB")"
  "${IM[@]}" "$SRC" -auto-orient -resize "480x270^" -gravity center -extent 480x270 \
    -colorspace sRGB -quality "$MEDIA_THUMB_Q" -strip "$THUMB"
  ok "wrote thumb $THUMB"
fi
