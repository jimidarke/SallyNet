#!/usr/bin/env bash
# Deploy the LTE modem monitor (poller + systemd service + env) to campingpi.
# Works over the WireGuard tunnel using the sally_campingpi key — see
# subsystems/network/remote-access-vpn.md. The LuCI password is read from the
# repo .env (QX210_LUCI_PASS) and written to /etc/sally/lte-monitor.env (0600).
#
# Uses the SINGLE-CONNECTION base64 path (one SSH, files inlined) rather than
# multi-hop scp — the ops gotcha in remote-access-vpn.md: scp stalls under the
# 3-4 s bufferbloat when Sally is streaming. Override via env: PI_HOST PI_USER SSH_KEY.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/sally-helpers.sh
. "$REPO/scripts/lib/sally-helpers.sh"

PI_HOST="${PI_HOST:-10.66.12.216}"   # over-the-tunnel address (local LAN: 192.168.2.216)
PI_USER="${PI_USER:-pi}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/sally_campingpi}"
SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)

require_cmd ssh base64

# Secrets + router facts from the repo .env (gitignored), with sane fallbacks.
if [ -f "$REPO/.env" ]; then set -a; . "$REPO/.env"; set +a; fi
: "${QX210_HOST:=192.168.2.1}"
: "${QX210_LUCI_USER:=admin}"
: "${QX210_LUCI_PASS:?set QX210_LUCI_PASS in $REPO/.env or the environment}"
: "${QX210_WAN_CELL_IFACE:=wwan0}"

ENV_CONTENT="$(cat <<EOF
QX210_HOST=$QX210_HOST
QX210_LUCI_USER=$QX210_LUCI_USER
QX210_LUCI_PASS=$QX210_LUCI_PASS
LTE_IFACE=$QX210_WAN_CELL_IFACE
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
MQTT_PREFIX=sally/telemetry/lte
INTERVAL=10
HA_DISCOVERY=1
HA_PREFIX=homeassistant
EOF
)"

PY_B64="$(base64 -w0 "$REPO/scripts/lte-monitor.py")"
SVC_B64="$(base64 -w0 "$REPO/configs/network/sally-lte-monitor.service")"
ENV_B64="$(printf '%s\n' "$ENV_CONTENT" | base64 -w0)"

header "deploying lte-monitor to $PI_USER@$PI_HOST (single connection)"
ssh "${SSH_OPTS[@]}" "$PI_USER@$PI_HOST" "
  set -e
  sudo mkdir -p /opt/sally/net /etc/sally
  printf '%s' '$PY_B64'  | base64 -d | sudo tee /opt/sally/net/lte-monitor.py >/dev/null
  sudo chmod 0755 /opt/sally/net/lte-monitor.py
  printf '%s' '$SVC_B64' | base64 -d | sudo tee /etc/systemd/system/sally-lte-monitor.service >/dev/null
  printf '%s' '$ENV_B64' | base64 -d | sudo tee /etc/sally/lte-monitor.env >/dev/null
  sudo chmod 0600 /etc/sally/lte-monitor.env
  sudo systemctl daemon-reload
  sudo systemctl enable --now sally-lte-monitor.service
"
ok "installed + service enabled"

header "status"
ssh "${SSH_OPTS[@]}" "$PI_USER@$PI_HOST" \
  'sleep 3; systemctl --no-pager --full status sally-lte-monitor.service | head -10; echo "-- recent log --"; journalctl -u sally-lte-monitor.service -n 12 --no-pager'
