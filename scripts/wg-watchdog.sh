#!/usr/bin/env bash
# SallyNet WireGuard site-node watchdog — runs ON campingpi (as root, via the
# sally-wg-watchdog.timer every ~60s). Keeps the dial-out tunnel (wg-home) alive
# through the two failure modes the stock wg-quick unit can't recover from:
#
#   1. Boot race — campingpi boots faster than the QX210 acquires LTE. wg-quick
#      is Type=oneshot: if DNS for the hub can't resolve at boot it fails and
#      NEVER retries. (oneshot units reject Restart=, so this watchdog IS the
#      retry: it (re)starts the unit until the uplink is up.)
#   2. DNS staleness — wg-quick resolves the Endpoint hostname only once, at
#      setconf time. The hub (DarkeRouter) sits behind hub.example.net dynamic DNS, so
#      a hub WAN-IP change leaves us firing keepalives at a dead address forever.
#
# Self-contained on purpose (deployed standalone to /opt/sally/net/); output goes
# to the systemd journal. See subsystems/network/remote-access-vpn.md.
set -euo pipefail

WG_IF="${WG_IF:-wg-home}"
HUB_HOST="${HUB_HOST:-hub.example.net}"
HUB_PORT="${HUB_PORT:-51820}"
HUB_PUBKEY="${HUB_PUBKEY:-<hub-public-key>}"
STALE_AFTER="${STALE_AFTER:-150}"   # seconds without a handshake before we bounce
UNIT="wg-quick@${WG_IF}"

log() { printf '%s wg-watchdog: %s\n' "$(date '+%H:%M:%S')" "$*"; }

# 0. Ensure the tunnel unit is actually up (covers the boot race).
if ! systemctl is-active --quiet "$UNIT"; then
  log "unit $UNIT not active — (re)starting"
  systemctl restart "$UNIT" || log "restart failed (no uplink yet?) — retry next tick"
  exit 0
fi

# 1. Re-resolve the hub DDNS hostname and update the peer endpoint if it moved.
resolve() {
  if command -v dig >/dev/null 2>&1; then
    dig +short A "$1" | grep -Em1 '^[0-9]+\.[0-9]'
  else
    getent ahostsv4 "$1" | awk '{print $1; exit}'
  fi
}
new_ip="$(resolve "$HUB_HOST" || true)"
cur_ep="$(wg show "$WG_IF" endpoints | awk -v k="$HUB_PUBKEY" '$1==k{print $2}')"
cur_ip="${cur_ep%:*}"
if [ -n "$new_ip" ] && [ "$new_ip" != "$cur_ip" ]; then
  log "hub endpoint moved ${cur_ip:-none} -> ${new_ip} — updating peer"
  wg set "$WG_IF" peer "$HUB_PUBKEY" endpoint "${new_ip}:${HUB_PORT}"
  exit 0   # let keepalive take a cycle to re-handshake before we consider a bounce
fi

# 2. Handshake watchdog — if the tunnel is wedged, bounce it to re-establish.
hs="$(wg show "$WG_IF" latest-handshakes | awk -v k="$HUB_PUBKEY" '$1==k{print $2}')"
now="$(date +%s)"
age=$(( now - ${hs:-0} ))
if [ "${hs:-0}" -eq 0 ] || [ "$age" -gt "$STALE_AFTER" ]; then
  log "handshake stale (${age}s > ${STALE_AFTER}s) — restarting $UNIT"
  systemctl restart "$UNIT"
else
  log "ok (handshake ${age}s ago, hub ${cur_ip})"
fi
