#!/usr/bin/env bash
# Deploy the media pipeline (scripts + conf + systemd units) to campingpi.
# Installs the track-logger service (always-on) + the nightly encode timer.
# Reads Pi creds from the repo-root .env (PI_HOST, PI_USER, PI_PASSWORD) — same as deploy-sally-api.sh.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/sally-helpers.sh
. "$HERE/lib/sally-helpers.sh"
REPO="$(cd "$HERE/.." && pwd)"
set -a; . "$REPO/.env"; set +a
export SSHPASS="$PI_PASSWORD"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)

header "ensuring /opt/sally/media + /var/lib/sally on $PI_HOST"
sshpass -e ssh "${SSH_OPTS[@]}" "$PI_USER@$PI_HOST" \
  "sudo mkdir -p /opt/sally/media/lib /var/lib/sally && sudo chown -R $PI_USER:$PI_USER /opt/sally /var/lib/sally"

header "syncing scripts"
sshpass -e rsync -az -e "ssh ${SSH_OPTS[*]}" \
  "$REPO/scripts/media-ingest.sh" "$REPO/scripts/media-encode-video.sh" \
  "$REPO/scripts/media-encode-photo.sh" "$REPO/scripts/media-extract-meta.py" \
  "$REPO/scripts/media-track-logger.py" "$REPO/scripts/media-reindex.py" \
  "$REPO/scripts/trip-eta-refresh.py" \
  "$PI_USER@$PI_HOST:/opt/sally/media/"
sshpass -e rsync -az -e "ssh ${SSH_OPTS[*]}" \
  "$REPO/scripts/lib/" "$PI_USER@$PI_HOST:/opt/sally/media/lib/"
sshpass -e ssh "${SSH_OPTS[@]}" "$PI_USER@$PI_HOST" "chmod +x /opt/sally/media/*.sh /opt/sally/media/*.py"

header "installing conf (only if absent — never clobber a tuned conf)"
sshpass -e scp "${SSH_OPTS[@]}" "$REPO/configs/media/sally-media.conf" \
  "$PI_USER@$PI_HOST:/tmp/sally-media.conf"
sshpass -e ssh "${SSH_OPTS[@]}" "$PI_USER@$PI_HOST" \
  "[ -f /opt/sally/media/sally-media.conf ] || mv /tmp/sally-media.conf /opt/sally/media/sally-media.conf; rm -f /tmp/sally-media.conf"

header "installing systemd units"
for u in media-track-logger.service media-encode.service media-encode.timer; do
  sshpass -e scp "${SSH_OPTS[@]}" "$REPO/configs/media/$u" "$PI_USER@$PI_HOST:/tmp/$u"
  sshpass -e ssh "${SSH_OPTS[@]}" "$PI_USER@$PI_HOST" "sudo mv /tmp/$u /etc/systemd/system/$u"
done
# trip ETA refresher (telemetry unit dir) — 60s timer, no-ops without an active trip.
for u in trip-eta.service trip-eta.timer; do
  sshpass -e scp "${SSH_OPTS[@]}" "$REPO/configs/telemetry/$u" "$PI_USER@$PI_HOST:/tmp/$u"
  sshpass -e ssh "${SSH_OPTS[@]}" "$PI_USER@$PI_HOST" "sudo mv /tmp/$u /etc/systemd/system/$u"
done
sshpass -e ssh "${SSH_OPTS[@]}" "$PI_USER@$PI_HOST" \
  "sudo systemctl daemon-reload \
   && sudo systemctl enable --now media-track-logger.service \
   && sudo systemctl enable --now media-encode.timer \
   && sudo systemctl enable --now trip-eta.timer \
   && sleep 1 && systemctl is-active media-track-logger.service && systemctl list-timers media-encode.timer trip-eta.timer --no-pager | head -4"

header "ensuring HDD tree exists"
sshpass -e ssh "${SSH_OPTS[@]}" "$PI_USER@$PI_HOST" \
  "MEDIA_HOME=\$(. /opt/sally/media/sally-media.conf; echo \$MEDIA_HOME); \
   mkdir -p \$MEDIA_HOME/{inbox,work,library/{trips,drone,memories,unsorted},originals,catalog/items,tracks,failed,logs}"

ok "deployed. verify:"
echo "    ssh $PI_USER@$PI_HOST 'tail -f /mnt/usb/home/tracks/*.gpx'   # breadcrumbs accumulating"
echo "    ssh $PI_USER@$PI_HOST 'sudo systemctl start media-encode.service' # drain inbox now"
