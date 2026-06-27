---
name: sallynet-pi-ops
description: >-
  Deploy to and maintain campingpi — the Raspberry Pi 3B+ that hosts all of
  SallyNet's always-on services (the sally-api Flask app on :8090, gpsd,
  mosquitto, the media + telemetry pipeline, the LTE monitor, the WireGuard site
  node). Use whenever the task is to push, deploy, or update code to the Pi,
  restart/enable/check a Sally service, tail its logs, run the media or telemetry
  pipeline, preseed map tiles, or do Pi maintenance — anything touching
  campingpi, /opt/sally, /var/lib/sally, or the scripts/deploy-*.sh scripts.
  Trigger on phrasings like "push my sally-api change", "redeploy the map
  service", "the encode timer isn't running", "tail the api logs", "preseed tiles
  for our trip", "restart gpsd". Action-enabling — it runs deploys and restarts,
  but always after the preflight safety checks. For the tunnel, router, or
  reachability from home, use sallynet-networking; for what the API serves users,
  use sallynet-interfaces.
---

# SallyNet Pi ops — deploy + maintain campingpi

`campingpi` is a Raspberry Pi 3B+ (wired `eth0`, `192.168.2.216` / `10.66.12.216`).
It is the RetroPie box **and** the Phase-0/2 always-on services host: `sally-api`
(Flask, `:8090`), `gpsd`, `mosquitto`, the media pipeline, the LTE monitor, and the
WireGuard site node. (At Phase 3 the services move to an Intel N100; the Pi reverts
to pure RetroPie. All paths are env-driven, so that migration is a repoint, not a
rewrite.)

This skill is **action-enabling with guardrails**: you may run the deploys and
service ops below, but run the preflight first and verify after. The deep per-script
and per-path detail lives in the references — this body is the safe operating
procedure.

## Preflight (run before any deploy or remote command)

1. **Pick the right address.** On SallyNet WiFi → `192.168.2.216`. Remote → bring the
   tunnel up first and use `10.66.12.216`:
   ```bash
   sudo wg-quick up ~/code/homeController/secrets/wg-clients/sally.conf
   ssh -i ~/.ssh/sally_campingpi pi@10.66.12.216 'echo ok; uptime'
   ```
2. **Confirm the link is healthy and not bloated.** If Sally is streaming, the
   cellular link bloats to ~3–4 s RTT and **multi-round-trip `rsync`/`scp` deploys
   stall**. Two of the four deploy scripts use rsync/scp (see table) — prefer running
   those on-LAN, or when the link is quiet. The LTE monitor's MQTT `lte/state` topic
   tells you current throughput/signal (see [`sallynet-networking`](../sallynet-networking/SKILL.md)).
3. **Know what you'll restart.** Each deploy script restarts specific units — don't
   bounce a service the user didn't ask about. The table says which.
4. **Watch out for the failing HDD.** `/mnt/usb/home` (the exFAT media disk) has an
   **unrecovered bad-sector band** — avoid heavy writes there; the crash-safe
   read-models already live on the SD card (`/var/lib/sally`).

## Deploy scripts

All live in `scripts/`, read the repo `.env`, and are idempotent. `$PI_HOST` comes
from `.env` (defaults to the tunnel addr `10.66.12.216`; override `PI_HOST=192.168.2.216`
when you're on SallyNet WiFi).

| Script | Auth / transport | Pushes → target | Restarts | Verify |
|---|---|---|---|---|
| `deploy-sally-api.sh` | `sshpass`+`PI_PASSWORD`, **rsync `--delete`** (multi-RTT) | `services/sally-api/` → `/opt/sally/sally-api/`; writes `/opt/sally/sally-api.env` (0600, `TILE_API_KEY`); installs `sally-api.service` | `sally-api.service` | `curl -s http://$PI:8090/api/health` (and `/api/state`) |
| `deploy-media-worker.sh` | `sshpass`+`PI_PASSWORD`, rsync/scp | media scripts → `/opt/sally/media/`; conf only if absent; creates the HDD tree | `media-track-logger.service`, `media-encode.timer`, `trip-eta`/`waypoint-eta`/`poi-refresh` timers | `systemctl is-active media-track-logger`; `systemctl list-timers` |
| `deploy-lte-monitor.sh` | **key** `sally_campingpi`, **base64-inline single-connection** (tunnel-safe) | `lte-monitor.py` → `/opt/sally/net/`; env → `/etc/sally/lte-monitor.env` (0600) | `sally-lte-monitor.service` | `mosquitto_sub -t sally/telemetry/lte/state` |
| `deploy-wg-watchdog.sh` | **key**, multi-hop scp (can stall under load) | `wg-watchdog.sh` → `/opt/sally/net/`; installs timer | `sally-wg-watchdog.timer` | manual run prints `ok (handshake …)` |

**The transport split matters.** The api + media deploys use password+rsync/scp, which
is fine on-LAN but is the multi-RTT path that stalls under bufferbloat. Only
`deploy-lte-monitor.sh` uses the single-connection base64-inline pattern that survives a
loaded tunnel — copy that pattern if you add a tunnel-only deploy. After any
`sally-api` deploy, confirm `/api/health` returns `{ok: true}` before calling it done.

Per-script line-level detail: [`references/deploy-scripts.md`](references/deploy-scripts.md).

## Services + paths (where everything lives on the Pi)

- `/opt/sally/sally-api/` — Flask app (rsync target). `sally-api.service`: `Type=simple`,
  `User=pi`, `ExecStart=/usr/bin/python3 /opt/sally/sally-api/app.py`, `Restart=on-failure`,
  `EnvironmentFile=-/opt/sally/sally-api.env`, `After=gpsd.socket`.
- `/opt/sally/media/` — pipeline scripts + `sally-media.conf`.
- `/opt/sally/net/` — `lte-monitor.py`, `wg-watchdog.sh`.
- `/var/lib/sally/` — **SD card**, atomic JSON read-models (crash-safe, *not* on the
  failing HDD): `catalog.json`, `trips.json`, `route.json`, `waypoint-route.json`,
  `waypoints.json`, `poi-cache.json`, `fuel-log.json`, `tracks/*.gpx`.
- `/mnt/usb/home/` — **HDD** media library tree (`inbox work library/{trips,drone,
  memories,unsorted} originals catalog/items maptiles failed logs`). ⚠️ failing disk.
- `/etc/sally/lte-monitor.env` (0600) · `/etc/wireguard/wg-home.conf` (site node).

systemd units installed by the deploys: `sally-api`, `media-track-logger`,
`media-encode.{service,timer}`, `trip-eta.{service,timer}`, `waypoint-eta.{service,timer}`,
`poi-refresh.{service,timer}`, `sally-lte-monitor`, `sally-wg-watchdog.{service,timer}`.
Full unit catalog + cadence: [`references/services-and-paths.md`](references/services-and-paths.md).

## Common ops

```bash
# Reach the Pi (remote): bring the tunnel up first (preflight), then:
PI=10.66.12.216   # or 192.168.2.216 on-LAN
ssh -i ~/.ssh/sally_campingpi pi@$PI

# Service status / restart / logs
sudo systemctl status sally-api.service
sudo systemctl restart sally-api.service
journalctl -u sally-api.service -f             # live logs (swap unit name)

# Drain the upload inbox now instead of waiting for 02:00
sudo systemctl start media-encode.service

# Preseed offline map tiles for a route corridor (HDD cache; bounded by PRESEED_MAX_TILES)
python3 /opt/sally/media/map-preseed.py 52.0 -118.5 53.6 -116.0 8 14   # Jasper/Icefields

# Health
curl -s http://$PI:8090/api/health | jq
vcgencmd get_throttled                         # under-voltage canary (want 0x0)
```

## Maintenance guardrails (and the why)

- **Stay on Raspbian Buster — never `dist-upgrade`.** Buster is EOL; apt is repointed to
  `legacy.raspbian.org`. The media pipeline carries version-pinned ffmpeg 4.1 workarounds
  (`-vsync cfr`, `trunc(iw/2)*2`) and the services run on Python 3.7. An upgrade breaks
  ffmpeg, the gpsd build, and the stdlib-only scripts. The N100 is the real upgrade path.
- **The media HDD is failing.** Seagate ST1000LM037 has an unrecovered-read band that has
  degraded to write faults on some library dirs. Back up before heavy writes; tile reads
  are best-effort (an I/O error becomes a cache miss, never a crash). Diagnosis:
  `subsystems/media/hdd-failure-2026-06-26.md`. The SD read-models are the durable copy.
- **Chronic under-voltage.** `vcgencmd get_throttled` has logged non-zero — a 12 V→5 V feed
  issue. It destabilizes the tunnel and timers; the power node deploy (#4) is itself gated
  on getting this to `0x0`. Fix the feed (`subsystems/power/`), don't just paper over it.
- **WiFi + BT are disabled; the Pi is wired-only.** This frees the PL011 UART for the
  router serial link and avoids the single-radio WiFi/BT time-slice conflict. Don't
  re-enable them while the Pi is the services host.
- **Don't clobber tuned config.** `deploy-media-worker.sh` installs `sally-media.conf`
  *only if absent*; `/opt/sally/sally-api.env` lives outside the rsync dir so `--delete`
  can't remove it. Preserve that discipline.

## Canonical sources

- `scripts/deploy-*.sh`, `scripts/lib/sally-helpers.sh` (shared `header/ok/warn/fail`)
- `configs/{media,telemetry,network}/*` — the systemd units + `sally-media.conf`
- `services/sally-api/sallyconf.py` — every env-overridable path/port default
- `CLAUDE.md` (the "File Paths on Sally's hardware" block) · `subsystems/compute/README.md`

## Related skills

- [`sallynet-networking`](../sallynet-networking/SKILL.md) — the tunnel, addresses, LTE
- [`sallynet-interfaces`](../sallynet-interfaces/SKILL.md) — what the deployed `:8090` API serves
