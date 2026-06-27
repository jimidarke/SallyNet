#!/usr/bin/env bash
# Deploy the WireGuard site-node watchdog (script + systemd timer) to campingpi.
# Works over the WireGuard tunnel using the sally_campingpi key — see
# subsystems/network/remote-access-vpn.md. Override via env: PI_HOST PI_USER SSH_KEY.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/sally-helpers.sh
. "$REPO/scripts/lib/sally-helpers.sh"

PI_HOST="${PI_HOST:-10.66.12.216}"   # over-the-tunnel address (local LAN: 192.168.2.216)
PI_USER="${PI_USER:-pi}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/sally_campingpi}"
SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)

require_cmd ssh scp

header "deploying wg-watchdog to $PI_USER@$PI_HOST"
ssh "${SSH_OPTS[@]}" "$PI_USER@$PI_HOST" "sudo mkdir -p /opt/sally/net"
scp "${SSH_OPTS[@]}" "$REPO/scripts/wg-watchdog.sh"                       "$PI_USER@$PI_HOST:/tmp/wg-watchdog.sh"
scp "${SSH_OPTS[@]}" "$REPO/configs/network/sally-wg-watchdog.service"    "$PI_USER@$PI_HOST:/tmp/sally-wg-watchdog.service"
scp "${SSH_OPTS[@]}" "$REPO/configs/network/sally-wg-watchdog.timer"      "$PI_USER@$PI_HOST:/tmp/sally-wg-watchdog.timer"

ssh "${SSH_OPTS[@]}" "$PI_USER@$PI_HOST" '
  set -e
  sudo install -m 0755 /tmp/wg-watchdog.sh /opt/sally/net/wg-watchdog.sh
  sudo mv /tmp/sally-wg-watchdog.service /etc/systemd/system/sally-wg-watchdog.service
  sudo mv /tmp/sally-wg-watchdog.timer   /etc/systemd/system/sally-wg-watchdog.timer
  sudo systemctl daemon-reload
  sudo systemctl enable --now sally-wg-watchdog.timer
'
ok "installed + timer enabled"

header "status"
ssh "${SSH_OPTS[@]}" "$PI_USER@$PI_HOST" \
  'systemctl --no-pager list-timers sally-wg-watchdog.timer 2>/dev/null | head -3; echo "-- one manual run --"; sudo /opt/sally/net/wg-watchdog.sh'
