#!/usr/bin/env bash
# media-encode-video.sh — normalize any source video to the single SallyNet "gold
# standard" Roku-friendly profile, then make a 480x270 poster.
#
#   H.264 High@L4.2 / yuv420p / fit-within-1920x1080 (downscale-only, AR preserved) /
#   CFR (nearest std fps) / 2 s GOP / CRF + maxrate cap / AAC-LC stereo 48k 192k / +faststart
#
# The profile is what the Roku Premiere decodes cleanly over LAN WiFi. moov-at-front
# (+faststart) and CFR are mandatory for Roku progressive MP4. Codec/quality knobs come
# from sally-media.conf (or env), defaulting to H.264 so this runs anywhere.
#
# Usage:  media-encode-video.sh <src> <out.mp4> [<poster.jpg>]
# Standalone-callable by the remote worker; deterministic so re-runs overwrite.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/sally-helpers.sh
. "$HERE/lib/sally-helpers.sh"
load_conf

SRC="${1:?usage: media-encode-video.sh <src> <out.mp4> [<poster.jpg>]}"
OUT="${2:?usage: media-encode-video.sh <src> <out.mp4> [<poster.jpg>]}"
POSTER="${3:-}"

# --- tunables (conf/env overridable) -----------------------------------------
: "${MEDIA_CODEC:=h264}"      # h264 | h265
: "${MEDIA_CRF:=20}"          # visually-transparent target
: "${MEDIA_MAXRATE:=12M}"     # cap so a clip never overruns the Roku's WiFi
: "${MEDIA_BUFSIZE:=24M}"
: "${MEDIA_PRESET:=slow}"
: "${MEDIA_MAX_W:=1920}"
: "${MEDIA_MAX_H:=1080}"
: "${MEDIA_AUDIO_KBPS:=192}"
: "${MEDIA_FFMPEG:=ffmpeg}"
: "${MEDIA_FFPROBE:=ffprobe}"
: "${MEDIA_THREADS:=0}"       # 0 = ffmpeg auto; the Pi-overnight path sets 2

require_cmd "$MEDIA_FFMPEG" "$MEDIA_FFPROBE" awk

[ -f "$SRC" ] || die "source not found: $SRC"
mkdir -p "$(dirname "$OUT")"

# --- pick the CFR flag for this ffmpeg (Buster 4.x = -vsync; >=5 = -fps_mode) --
cfr_flag() {
  local v major
  v="$("$MEDIA_FFMPEG" -version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1)"
  major="${v%%.*}"
  if [ -n "${major:-}" ] && [ "$major" -ge 5 ] 2>/dev/null; then
    echo "-fps_mode cfr"
  else
    echo "-vsync cfr"
  fi
}

# --- target frame rate: nearest standard of {24,25,30,60}, capped at 60 -------
target_fps() {
  local raw num den fps
  raw="$("$MEDIA_FFPROBE" -v error -select_streams v:0 \
        -show_entries stream=avg_frame_rate -of default=nk=1:nw=1 "$SRC" 2>/dev/null | head -1)"
  case "$raw" in
    ""|"0/0"|"N/A") echo 30; return;;
  esac
  num="${raw%%/*}"; den="${raw##*/}"; [ "$den" = "0" ] && den=1
  fps="$(awk -v n="$num" -v d="$den" 'BEGIN{ if(d==0)d=1; r=n/d;
        split("24 25 30 60", a, " "); best=a[1]; bd=1e9;
        for(i=1;i<=4;i++){ x=(r-a[i]); if(x<0)x=-x; if(x<bd){bd=x; best=a[i]} }
        print best }')"
  echo "${fps:-30}"
}

CFR="$(cfr_flag)"
FPS="$(target_fps)"
GOP=$(( FPS * 2 ))

# Fit within MAX_W x MAX_H, AR preserved, never upscale (min() trick handles
# portrait too: a 1080x1920 clip lands at ~608x1080 — full height, Roku letterboxes).
# A second scale truncates to even dims (yuv420p needs even); done this way because
# the Pi's ffmpeg 4.1 lacks scale's force_divisible_by (added in 4.4).
VF="scale='min(iw,${MEDIA_MAX_W})':'min(ih,${MEDIA_MAX_H})':force_original_aspect_ratio=decrease,scale='trunc(iw/2)*2':'trunc(ih/2)*2',format=yuv420p"

# --- codec-specific video args ------------------------------------------------
if [ "$MEDIA_CODEC" = "h265" ] || [ "$MEDIA_CODEC" = "hevc" ]; then
  VARGS=( -c:v libx265 -preset "$MEDIA_PRESET" -crf "$MEDIA_CRF"
          -maxrate "$MEDIA_MAXRATE" -bufsize "$MEDIA_BUFSIZE"
          -x265-params "keyint=${GOP}:min-keyint=${GOP}:scenecut=0"
          -tag:v hvc1 )
else
  VARGS=( -c:v libx264 -profile:v high -level:v 4.2 -preset "$MEDIA_PRESET" -crf "$MEDIA_CRF"
          -maxrate "$MEDIA_MAXRATE" -bufsize "$MEDIA_BUFSIZE"
          -x264-params "keyint=${GOP}:min-keyint=${GOP}:scenecut=0" )
fi

header "encode video → $MEDIA_CODEC ${FPS}fps (GOP ${GOP}) crf ${MEDIA_CRF} cap ${MEDIA_MAXRATE}"
# shellcheck disable=SC2086
"$MEDIA_FFMPEG" -y -hide_banner -loglevel warning -threads "$MEDIA_THREADS" \
  -i "$SRC" -map 0:v:0 -map "0:a:0?" \
  -vf "$VF" -r "$FPS" $CFR \
  "${VARGS[@]}" \
  -c:a aac -b:a "${MEDIA_AUDIO_KBPS}k" -ac 2 -ar 48000 \
  -movflags +faststart \
  -f mp4 "$OUT"
ok "wrote $OUT"

if [ -n "$POSTER" ]; then
  mkdir -p "$(dirname "$POSTER")"
  "$MEDIA_FFMPEG" -y -hide_banner -loglevel error -i "$OUT" \
    -vf "thumbnail,scale=480:270:force_original_aspect_ratio=increase,crop=480:270" \
    -frames:v 1 -q:v 3 -f image2 "$POSTER"
  ok "wrote poster $POSTER"
fi
