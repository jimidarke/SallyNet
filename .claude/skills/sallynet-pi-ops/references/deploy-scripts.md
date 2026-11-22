# Deploy scripts — line-level reference

All in `scripts/`, all `set -euo pipefail`, all source the repo `.env`. Two transport
families: **password + rsync/scp** (api, media — multi-RTT, fine on-LAN) and **key +
single-connection base64 / scp** (lte-monitor, wg-watchdog — for over-the-tunnel).

## `deploy-sally-api.sh`

- **Auth:** `sshpass` with `SSHPASS=$PI_PASSWORD`; `$PI_USER@$PI_HOST` from `.env`.
- **Steps:**
  1. `ssh … "sudo mkdir -p /opt/sally/sally-api && sudo chown -R pi:pi /opt/sally"`
  2. `rsync -az --delete services/sally-api/ → /opt/sally/sally-api/`
  3. write `/opt/sally/sally-api.env` with `umask 077` (mode 600), containing
     `TILE_API_KEY=…` — **outside** the rsync'd dir so `--delete` never wipes it.
  4. scp `configs/media/sally-api.service` → `/etc/systemd/system/`, then
     `daemon-reload && enable && restart && systemctl is-active`.
- **Verify:** `curl -s http://$PI_HOST:8090/api/state | jq` (the script prints this);
  `/api/health` is the lighter liveness check.
- **Gotcha:** `rsync --delete` makes `/opt/sally/sally-api/` an exact mirror of the repo
  dir — any stray file on the Pi is removed. The runtime env file is deliberately one
  level up to survive this.

## `deploy-media-worker.sh`

- **Auth:** `sshpass`+`PI_PASSWORD`. Sources `scripts/lib/sally-helpers.sh`.
- **Steps:**
  1. mkdir `/opt/sally/media/lib` + `/var/lib/sally`, chown to `pi`.
  2. rsync the pipeline scripts → `/opt/sally/media/`:
     `media-ingest.sh`, `media-encode-video.sh`, `media-encode-photo.sh`,
     `media-extract-meta.py`, `media-track-logger.py`, `media-reindex.py`,
     `trip-eta-refresh.py`, `waypoint-eta-refresh.py`, `poi-refresh.py`,
     `map-preseed.py`; plus `scripts/lib/` → `/opt/sally/media/lib/`. `chmod +x`.
  3. install `sally-media.conf` **only if absent** (never clobber a tuned conf).
  4. install units: `media-track-logger.service`, `media-encode.service`,
     `media-encode.timer` (from `configs/media/`); `trip-eta`, `waypoint-eta`,
     `poi-refresh` `.service`+`.timer` (from `configs/telemetry/`).
  5. `daemon-reload && enable --now` the track-logger + all four timers.
  6. create the media tree under `$MEDIA_HOME` (from `sally-media.conf`):
     `{inbox,work,library/{trips,drone,memories,unsorted},originals,catalog/items,tracks,failed,logs}`.
- **Verify:** `systemctl is-active media-track-logger`; `systemctl list-timers`.
  Drain inbox now: `sudo systemctl start media-encode.service`.

## `deploy-lte-monitor.sh`  (the tunnel-safe pattern to copy)

- **Auth:** key `~/.ssh/sally_campingpi`; `PI_HOST` defaults to `10.66.12.216`.
- **Why base64-inline:** one SSH connection, files `base64 -w0` on the dev box and
  `base64 -d | sudo tee` on the Pi — avoids the multi-round-trip scp that stalls under
  the 3–4 s bufferbloat when Sally streams.
- **Steps:** build `ENV_CONTENT` from `.env` (`QX210_LUCI_PASS` required;
  `QX210_HOST`/`QX210_LUCI_USER`/`QX210_WAN_CELL_IFACE` defaulted), then in one ssh:
  decode `lte-monitor.py` → `/opt/sally/net/` (0755), `sally-lte-monitor.service` →
  `/etc/systemd/system/`, env → `/etc/sally/lte-monitor.env` (0600);
  `daemon-reload && enable --now`. Env written: `QX210_HOST`, `QX210_LUCI_USER`,
  `QX210_LUCI_PASS`, `LTE_IFACE`, `MQTT_HOST=127.0.0.1`, `MQTT_PORT=1883`,
  `MQTT_PREFIX=sally/telemetry/lte`, `INTERVAL=10`, `HA_DISCOVERY=1`, `HA_PREFIX=homeassistant`.
- **Verify:** the script tails `journalctl -u sally-lte-monitor -n 12`; or
  `mosquitto_sub -h 192.168.2.216 -t 'sally/telemetry/lte/#' -v`.

## `deploy-wg-watchdog.sh`

- **Auth:** key `sally_campingpi`; `PI_HOST` defaults to `10.66.12.216`.
- **Transport:** multi-hop scp (3 files to `/tmp`, then `sudo install`/`mv`). The doc
  flags this can itself time out under bufferbloat — run it when the link is quiet.
- **Steps:** install `wg-watchdog.sh` → `/opt/sally/net/` (0755),
  `sally-wg-watchdog.{service,timer}` → `/etc/systemd/system/`,
  `daemon-reload && enable --now sally-wg-watchdog.timer`; then a manual run.
- **Verify:** the manual run logs e.g. `ok (handshake 70s ago, hub <hub-wan-ip>)`.

## Adding a new deploy

- If it must work over the tunnel under load → copy `deploy-lte-monitor.sh`'s
  base64-inline single-connection pattern.
- Keep secrets out of the app dir and `chmod 0600`; render them from `.env`, never
  commit them.
- Source `scripts/lib/sally-helpers.sh` for `header/ok/warn/fail` colored output.
