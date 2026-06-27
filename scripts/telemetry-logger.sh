#!/usr/bin/env bash
# telemetry-logger.sh — subscribe to SallyNet MQTT telemetry, append to daily JSONL.
#
# Why: the LTE monitor (sally-lte-monitor.service) and the ESP cabin node publish
# to MQTT, but nothing persists them — the data is live-only. This is the missing
# subscriber: it writes a durable time-series for the fuel-economy-vs-conditions
# correlation (subsystems/telemetry/README.md). Phase-0 stopgap on campingpi;
# superseded by Home Assistant's recorder once the broker is bridged to the
# homeController estate (the HA discovery configs are already published).
#
# Output: one JSON object per message appended to
#   $OUTDIR/YYYY-MM-DD.jsonl   e.g.
#   {"tst":1782541612,"topic":"sally/telemetry/lte/state","payload":"{...}"}
# `tst` is receipt time (epoch s). `payload` is always a JSON string; for the LTE
# topic it is itself JSON, so parse twice downstream
# (json.loads the line, then json.loads(rec["payload"])); cabin scalars are float().
#
# NB: records are built with jq, not mosquitto_sub's `-F '%j'`. The Buster
# mosquitto (1.5.7) has a buggy %j that escapes `"` as `4` (-> the char "4"),
# which corrupts any payload containing quotes (e.g. the LTE JSON). jq escapes
# correctly.
#
# Deployed to /opt/sally/telemetry/telemetry-logger.sh and run by
# sally-telemetry-logger.service. Tunables via environment (defaults below).
set -euo pipefail

BROKER="${BROKER:-localhost}"
PORT="${PORT:-1883}"
OUTDIR="${OUTDIR:-/var/lib/sally/telemetry}"
RETAIN_DAYS="${RETAIN_DAYS:-90}"   # prune *.jsonl older than this at startup; 0 = keep all

# Topics: per-node state + status + ESPHome sensor trees. Deliberately NOT the
# noisy `<node>/debug` topic the ESP nodes spew. New nodes that follow the
# convention (sally/telemetry/<node>/state | /status | /sensor/<x>/state) are
# captured automatically.
TOPICS=(
  -t 'sally/telemetry/+/state'
  -t 'sally/telemetry/+/status'
  -t 'sally/telemetry/+/sensor/#'
)

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; CYAN=$'\033[36m'; NC=$'\033[0m'
header(){ printf '%s\n' "${CYAN}== $* ==${NC}"; }
ok(){ printf '%s\n' "${GREEN}ok${NC} $*"; }
warn(){ printf '%s\n' "${YELLOW}warn${NC} $*"; }
fail(){ printf '%s\n' "${RED}fail${NC} $*" >&2; }

mkdir -p "$OUTDIR"

if [[ "$RETAIN_DAYS" -gt 0 ]]; then
  pruned=$(find "$OUTDIR" -maxdepth 1 -name '*.jsonl' -type f -mtime "+$RETAIN_DAYS" -print -delete 2>/dev/null | wc -l)
  [[ "$pruned" -gt 0 ]] && warn "pruned $pruned file(s) older than ${RETAIN_DAYS}d"
fi

header "telemetry-logger -> $OUTDIR (broker $BROKER:$PORT, retain ${RETAIN_DAYS}d)"

# stdbuf -oL forces line buffering so each message hits disk promptly (mosquitto_sub
# block-buffers when its stdout is a pipe). `-F '%t %p'` gives the raw topic +
# unmodified payload; jq then builds a correctly-escaped record. printf '%(...)T'
# is a bash builtin, so the daily-filename roll costs no subprocess per line.
stdbuf -oL mosquitto_sub -h "$BROKER" -p "$PORT" -F '%t %p' "${TOPICS[@]}" |
while IFS=' ' read -r topic payload; do
  printf -v day '%(%Y-%m-%d)T' -1
  if ! jq -cn --arg t "$topic" --arg p "$payload" \
        '{tst:(now|floor), topic:$t, payload:$p}' >> "$OUTDIR/$day.jsonl"; then
    warn "skipped unparseable message on ${topic:-?}"
  fi
done
