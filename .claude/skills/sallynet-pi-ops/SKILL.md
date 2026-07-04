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
4. **The media disk is an SSD now.** `/mnt/usb` is a Crucial BX500 1TB **ext4** SSD
   (swapped in 2026-06-27, mounted by UUID with `nofail`; the old failing exFAT HDD is
   gone). It's healthy — but the Pi's USB power budget is tight, so **don't add a second
   bus-powered disk** (running two at once tripped a brown-out during the swap). The
   crash-safe read-models still live on the SD card (`/var/lib/sally`).

## Deploy scripts

All live in `scripts/`, read the repo `.env`, and are idempotent. `$PI_HOST` comes
from `.env` (defaults to the tunnel addr `10.66.12.216`; override `PI_HOST=192.168.2.216`
when you're on SallyNet WiFi).

| Script | Auth / transport | Pushes → target | Restarts | Verify |
|---|---|---|---|---|
| `deploy-sally-api.sh` | `sshpass`+`PI_PASSWORD`, **rsync `--delete`** (multi-RTT) | `services/sally-api/` → `/opt/sally/sally-api/`; writes `/opt/sally/sally-api.env` (0600, `TILE_API_KEY`); installs `sally-api.service` | `sally-api.service` | `curl -s http://$PI:8090/api/health` (and `/api/state`) |
| `deploy-media-worker.sh` | `sshpass`+`PI_PASSWORD`, rsync/scp | media scripts → `/opt/sally/media/`; conf only if absent; creates the media tree | `media-track-logger.service`, `media-encode.timer`, `trip-eta`/`waypoint-eta`/`poi-refresh` timers | `systemctl is-active media-track-logger`; `systemctl list-timers` |
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
  media SSD): `catalog.json`, `trips.json`, `route.json`, `waypoint-route.json`,
  `waypoints.json`, `poi-cache.json`, `view-state.json`, `fuel-log.json`, `tracks/*.gpx`.
- `/mnt/usb/home/` — **media SSD** library tree (`inbox work library/{trips,drone,
  memories,unsorted} originals catalog/items maptiles failed logs`); the `maptiles/`
  basemap cache lives here too. Crucial BX500 1TB ext4, UUID-mounted; the user's
  `movies/`+`tv/` (MiniDLNA) sit at the `/mnt/usb` top.
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

# Preseed offline map tiles for a route corridor (SSD cache; bounded by PRESEED_MAX_TILES)
python3 /opt/sally/media/map-preseed.py 52.0 -118.5 53.6 -116.0 8 14   # Jasper/Icefields

# Health
curl -s http://$PI:8090/api/health | jq
vcgencmd get_throttled                         # under-voltage canary (want 0x0)
```

## The layered map (render pipeline on the Pi)

`sally-api` bakes the dashboard map **server-side**: `mapgen.py` composites one flat PNG at
`GET /api/map.png` (the Roku `MapScreen` and the phone browser both just display it — no
client-side map engine). Layers stack over the basemap: **Sally's arrow**, the **breadcrumb
trail** (`trail.py` from `tracks/*.gpx`), **waypoints** (`waypoints.py`), and **POIs**
(`poi-cache.json`). Layer visibility + the base-source selector are shared state —
`POST /api/view` → `/var/lib/sally/view-state.json`, re-read by `/api/map.png` so every
browser and the Roku render identically.

- **Basemap tiles** come from a raster provider (Thunderforest by default; `TILE_API_KEY`
  lives in `/opt/sally/sally-api.env`) and cache **forever** on the SSD at
  `/mnt/usb/home/maptiles`. With no key the basemap drops to gap-fill and only the local
  layers draw — the screen still works offline.
- `tiles.py` carries a negative-cache + circuit breaker so a slow/throttling provider (or an
  LTE dead zone) degrades to cache-only instead of stalling a render; every tile read/write
  is best-effort (an unmount → cache miss, never a crash). Pre-seed a corridor before a trip
  with `map-preseed.py` (above) — after the 2026-06-27 disk swap the cache started empty.
- The map's ETA/POI feeds are the `trip-eta` / `waypoint-eta` / `poi-refresh` timers writing
  `route.json` / `waypoint-route.json` / `poi-cache.json` on the SD. `mapgen` reuses a
  cached frame (`MAP_MIN_RENDER_INTERVAL_S` moving, `MAP_PARKED_TTL_S` parked) so Roku polls
  don't re-render identical frames. Tuning detail: `subsystems/gps/map-tile-hardening.md`.

## Maintenance guardrails (and the why)

- **Stay on Raspbian Buster — never `dist-upgrade`.** Buster is EOL; apt is repointed to
  `legacy.raspbian.org`. The media pipeline carries version-pinned ffmpeg 4.1 workarounds
  (`-vsync cfr`, `trunc(iw/2)*2`) and the services run on Python 3.7. An upgrade breaks
  ffmpeg, the gpsd build, and the stdlib-only scripts. The N100 is the real upgrade path.
- **The media disk is an SSD (swapped 2026-06-27).** `/mnt/usb` = Crucial BX500 1TB ext4,
  UUID-mounted with `nofail`; the old failing Seagate exFAT HDD is gone. Tile/library I/O is
  still best-effort (an unmount or error → cache miss, never a crash). The SSD's `home/`
  library is **re-encodable from source, not backed up** — the SD read-models
  (`/var/lib/sally`) are the durable copy. History: `subsystems/media/hdd-failure-2026-06-26.md`.
- **Chronic under-voltage.** `vcgencmd get_throttled` has logged non-zero — a 12 V→5 V feed
  issue. It destabilizes the tunnel and timers; the power node deploy (#4) is itself gated
  on getting this to `0x0`. **Running two bus-powered disks at once will trip it** (a ~4 s
  brown-out during the 2026-06-27 disk swap; a single SSD now boots clean at `0x0`). Fix the
  feed (`subsystems/power/`), don't just paper over it.
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
