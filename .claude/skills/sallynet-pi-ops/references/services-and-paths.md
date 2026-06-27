# Services + filesystem map on campingpi

Authoritative: `CLAUDE.md` "File Paths on Sally's hardware" + `services/sally-api/sallyconf.py`.

## systemd units

| Unit | Type | Role | Cadence |
|---|---|---|---|
| `sally-api.service` | simple | Flask API on `:8090` (the Roku-facing surface) | always-on, `Restart=on-failure` |
| `media-track-logger.service` | simple | gpsd → daily GPX breadcrumbs to SD | always-on (every 15 s if moved >5 m) |
| `media-encode.service` + `.timer` | oneshot | drain `inbox/` → encode → library | nightly `02:00`, idle prio, `RandomizedDelaySec=300` |
| `trip-eta.{service,timer}` | oneshot | OSRM ETA to active-trip destination → `route.json` | every 60 s (no-op when no trip) |
| `waypoint-eta.{service,timer}` | oneshot | OSRM road-km to next waypoint + arrival auto-advance → `waypoint-route.json` | every 60 s |
| `poi-refresh.{service,timer}` | oneshot | Overpass RV/fuel/scenic POIs → `poi-cache.json` | every 5 min / after moving >10 km |
| `sally-lte-monitor.service` | simple | QX210 LuCI → MQTT `lte/state` | every 10 s, `Restart=always` |
| `sally-wg-watchdog.{service,timer}` | oneshot | keep the WG tunnel healthy | every 60 s |

The oneshot timer scripts (`trip-eta-refresh.py`, `waypoint-eta-refresh.py`,
`poi-refresh.py`) self-rate-limit and no-op cheaply when idle, so they never starve
RetroPie. `media-encode` runs at `Nice=15` / idle IO+CPU scheduling for the same reason.

## Filesystem

```
/opt/sally/
  sally-api/        # Flask app (rsync target of deploy-sally-api.sh)
    app.py sallyconf.py gpsd_client.py store.py trail.py waypoints.py
    tiles.py mapgen.py mapassets/ requirements.txt docs/fuel-log.md
  sally-api.env     # runtime secrets (TILE_API_KEY) — 0600, OUTSIDE the rsync dir
  media/            # pipeline scripts + lib/ + sally-media.conf
  net/              # lte-monitor.py, wg-watchdog.sh

/var/lib/sally/     # SD CARD — atomic, crash-safe read-models (NOT the failing HDD)
  catalog.json          # home-media read-model (rebuilt by media-reindex.py)
  trips.json            # active trip + waypoints (source of truth)
  route.json            # OSRM ETA cache (trip-eta-refresh.py)
  waypoint-route.json   # OSRM ETA to next waypoint (waypoint-eta-refresh.py)
  waypoints.json        # trip pins (phone-edited at /waypoints)
  poi-cache.json        # Overpass snapshot (poi-refresh.py)
  fuel-log.json         # structured fill-up history
  tracks/YYYY-MM-DD.gpx # daily breadcrumbs (media-track-logger.py)

/mnt/usb/home/      # HDD (exFAT, FAILING) — bulky media library tree
  inbox/ work/ library/{trips,drone,memories,unsorted}/
  originals/ catalog/items/ maptiles/ failed/ logs/

/etc/sally/lte-monitor.env     # QX210 creds + MQTT config (0600)
/etc/systemd/system/*.service|*.timer
/etc/wireguard/wg-home.conf    # WG site node (PostUp/PostDown carry the NETMAP rules)
/etc/default/gpsd              # gpsd device + '-n'
/etc/apt/sources.list*         # repointed to legacy.raspbian.org (Buster EOL)
/dev/serial0 -> ttyAMA0        # PL011 UART, freed for the router serial link
```

## Why SD vs HDD split

The read-models need crash-safe atomic writes and the HDD has a failing band — so the
small, wear-tolerant, frequently-rewritten state lives on the SD card (`/var/lib/sally`)
and only the bulky, disposable media + tile cache live on the HDD (`/mnt/usb/home`). A
tile read/write that hits the bad band degrades to a cache miss, never a crash. Keep new
durable state on the SD side.

## Pi → N100 migration (Phase 3)

Every path above is an env var in `sallyconf.py` (`MEDIA_ROOT`, `INBOX_DIR`, `TRACKS_DIR`,
`CATALOG_JSON`, …) and the broker host is a one-line `secrets.yaml` edit for the ESP
fleet. So moving services to the N100 is a repoint + re-enable, not a rewrite. The Roku
only needs its `SALLY_API_BASE` changed because the API contract is frozen.
