# Sally Dashboard API — Contract (frozen, versioned)

The **only** surface the SallyNet Roku channel knows about. The Roku is glass: it polls these
HTTP endpoints and renders. It never speaks MQTT, gpsd, or SQLite. Keeping this contract
stable is what makes the Pi → N100 migration a one‑line `SALLY_API_BASE` change with zero
Roku code edits.

- **Base URL:** `http://<brains-host>:8090` — `campingpi` today (`192.168.2.216:8090`, or
  `10.66.12.216:8090` over the `sally` WireGuard link). Migrates to the N100 at Phase 3.
- **Schema version:** `1`. Every payload carries `schemaVersion`. Breaking changes bump it
  and bump the Roku registry `sallyCacheV` to invalidate cached snapshots.
- **Auth:** none (trusted LAN). Do not expose beyond SallyNet/WireGuard.

## Endpoints

| Endpoint | Method | Status | Returns |
|---|---|---|---|
| `/api/state` | GET | **live (P0)** | full snapshot — the heartbeat the Roku polls |
| `/api/discovery` | GET | stub (P3) | `{schemaVersion, host, streams:{}}` — camera stream URLs |
| `/api/health` | GET | **live (P0)** | `{ok, gps_fix, ts}` quick liveness |
| `/api/map.png?w=&h=&z=&layers=&v=` | GET | **live (P2)** | server‑composited ambient map PNG centered on live GPS (basemap + breadcrumb trail + heading arrow + status strip) |
| `/map` | GET | **live (P2)** | browser viewer for the map PNG (manual refresh + zoom/layer toggles) — troubleshooting & off‑TV usage |
| `/api/view` | GET·POST | **live** | shared map view-state — layer visibility (+ reserved `baseSource`); every browser AND the Roku glass render the same layers |
| `/api/media?type=trips` | GET | **live (P1)** | home‑media collections (trips/drone/memories/unsorted) |
| `/api/media?type=movies\|tv\|kids` | GET | reserved | studio library — empty `collections` until built |
| `/api/collections/<id>` | GET | **live (P1)** | items (videos+photos) within one collection |
| `/media/<path>` | GET | **live (P1)** | faststart H.264 MP4 / JPEG, **HTTP Range** (206) |
| `/api/level.png` | GET | P2 | pre‑rendered leveling bubble PNG |
| `/api/photos[?collection=<id>]` | GET | **live (P5)** | flat slideshow list |
| `/api/qr.png` | GET | **live (P5)** | QR encoding the LAN upload URL guests scan |
| `/api/upload` · `/upload` | POST · GET | **live (P5)** | guest upload endpoint · mobile upload page |
| `/api/trip` · `/trip` | GET·POST · GET | **live (C2)** | trip store (active trip) · create/end trip · mobile trip-entry page |
| `/api/fuel-log` · `/fuel` | POST · GET | **live (C3)** | log a fill-up → `fuel-log.json` + `docs/fuel-log.md` · mobile fuel-entry page |
| `/api/waypoints` · `/waypoints` | GET·POST · GET | **live (P2)** | trip waypoint pins (list · add/delete/toggle/favourite/promote) · mobile pin-editor page; drawn on `/api/map.png` |

> **`/api/map.png` params** (all optional, additive — the server owns centre + zoom, so the
> Roku can fetch with just `?w=&h=&v=`): `w`,`h` = canvas size; `z` = `auto` (speed-based band,
> default) or a forced `10–15`; `layers` = CSV subset of
> `base,trail,poi,photos,waypoints,labels,status` — **a one-off override**; with NO `layers` param
> (the Roku case) the server renders the **shared `/api/view` state**, so every viewer converges;
> `v` = cache-buster the Roku sets to the latest `state.ts` so the Poster re-fetches the changed
> image (ignored by the render cache). An always-on **GPS-loss banner** is baked on when a fix has
> been missing past `SALLY_GPS_ALERT_AFTER_S` (it is not a toggleable layer). No `schemaVersion`
> bump — additive, and `/api/state` is unchanged. Design: `../gps/map-navigation-brainstorm.md`.

## `/api/state` schema (v1)

**Important:** unavailable sections are **OMITTED**, never sent as JSON `null`. `sally-api`
recursively prunes `None` before serializing. The Roku reads a missing key as `invalid` and
hides that widget. (A stored `null`/`invalid` would crash a SceneGraph `assocarray` field, so
the API must never emit one.) The block below shows the *full* shape; commented lines are the
sections that are simply absent until their phase lands.

```jsonc
{
  "schemaVersion": 1,
  "ts": 1750000000,                       // unix seconds (server clock)
  "mode": "driving|camping|parked|at_home|unknown",// instantaneous HINT; Roku applies hysteresis
  "gps": {                                 // LIVE from gpsd (P0)
    "fix": true, "mode": 3,                // mode: 0/1 none, 2 = 2D, 3 = 3D
    "lat": 53.546100, "lon": -113.493800,
    "speed_kmh": 0.1,                      // "heading" present only when moving (omitted when stationary)
    "alt_m": 669.2, "sats": 12, "sats_visible": 15, "hdop": 0.65,
    "time": "2026-06-26T06:55:18.000Z"     // gps time (UTC)
  },
  "nav": { "secondsSinceFix": 0, "hadFix": true },  // GPS liveness (nav-tick) — fix-age drives the map loss banner
  "drive": { "km_from_home": 0.0, "reverse": false },  // odo_km/trip_km omitted until available
  "trip": {                                // present only when a trip is ACTIVE (C2)
    "id": "jasper-run", "title": "Jasper Run",
    "destName": "Jasper, AB", "dest": { "lat": 52.87, "lon": -118.08 },
    "aboard": ["Jimi", "Alex", "kids"],
    "dateStart": "2026-07-04", "dateEnd": "2026-07-07",
    "km_to_dest": 142.0,                   // haversine, ALWAYS present (offline-safe)
    "eta": 1751650000, "roadKm": 320.5,    // OSRM cache (arrival unix s) — omitted if no fix/cache
    "etaSource": "osrm", "etaStaleSec": 47 // age of the cached ETA; Roku flags it stale > 600 s
  },
  "fuel": {                                // present only once a fill-up is logged (C3)
    "last": { "date": "...", "odo_km": 142400.0, "litres": 88.0, "total": 136.4, "l_100km": 22.0 },
    "avg_l_100km": 21.4, "fills": 7
  },
  "alerts": [],                            // [{ kind, sev, text, ts }] — e.g. {kind:"gps_lost",sev:"warn"} on signal loss
  "system": { "host": "campingpi", "uptime_s": 0, "throttled": "0x0" }
  // --- omitted until populated (never sent as null) ---
  //   "power":  { batt_v, batt_a, soc_pct, tte_h, shore, mains_w }   (P2)
  //   "tanks":  { fresh_pct, grey_pct, black_pct, propane_pct }      (P2)
  //   "env":    { in_c, out_c, engine_c, humidity, pressure_hpa }    (P2)
  //   "level":  { pitch_deg, roll_deg, level_ok }                    (P2)
  //   "systems":{ pump, furnace, city_water }                        (P2, additive)
  //   "cameras":{ rearview, dashcam }                                (P3)
  //   "audio":  { source, fm_on }                                    (P4)
}
```

**Field notes**
- `gps.speed_kmh` derived from gpsd TPV `speed` (m/s × 3.6). `heading` from TPV `track`
  (degrees true); omitted when stationary or no fix.
- `drive.km_from_home` is haversine to the saved home anchor (default Edmonton
  `53.5461,-113.4938`, radius 150 m). Configurable via `SALLY_HOME_LAT/LON/RADIUS_M`.
- `mode` is an instantaneous hint: `driving` if speed ≥ `SALLY_DRIVING_KMH` (10); else `at_home`
  if within `SALLY_HOME_RADIUS_M` (1000 m); else `camping` if an **active trip** has a destination
  pin and we're stopped within `SALLY_DEST_RADIUS_M` (250 m); else `parked`. `camping` therefore
  requires a trip — it cannot be inferred from GPS alone. The Roku `modeController` owns the real
  hysteresis (≥2 stable polls today; the 8 km/h ×5 s / <3 km/h ×3 min curve is aspirational).
- `trip` is built from the SD trip store (`/var/lib/sally/trips.json`, written by `/api/trip`).
  `eta`/`roadKm`/`etaSource`/`etaStaleSec` come from the OSRM cache (`/var/lib/sally/route.json`,
  refreshed out-of-band by `scripts/trip-eta-refresh.py` every 60 s) — omitted when there's no
  cached route, leaving `km_to_dest` (straight-line) as the offline fallback.
- `fuel` is derived from `/var/lib/sally/fuel-log.json`; `l_100km` is per-tank (litres ÷ odometer
  delta to the previous fill), `avg_l_100km` is the running mean over fills that have one.
- `system.throttled` is `vcgencmd get_throttled` — the under‑voltage canary surfaced on the
  Systems screen.
- Sensor blocks (`power`/`tanks`/`env`/`level`/`systems`/`cameras`/`audio`) are **omitted** until
  their phase fills them — never emitted as `null`.
- `env` is **flat** (one `in_c`/`out_c`/`engine_c`), populated from the canonical nodes
  (`in_c` = cabin, `out_c` = the fixed outside/vent sensor, `engine_c` = the DS18B20 in the bay).
  The telemetry collector keeps **every per-node reading** (bunk, the portable fireside `camp` node,
  …) in SQLite for logging/Grafana; only these few surface here so the Roku tile stays simple.
- `systems` carries non-invasive **machine-state booleans** the `power`/`tanks` blocks don't cover:
  `pump`/`furnace` are derived from the power node's Tier-2 hall-clamp branch currents (current over
  a threshold ⇒ running); `city_water` from an optional inlet pressure switch. Gas/propane is never
  sensed here. Additive (no `schemaVersion` bump) — node detail in `subsystems/telemetry/esp-fleet.md`.

## Home media (P1/P5)

Home‑made content (camping trips, family memories, drone footage) is a **new collections
category**, additive to schema v1 (the Roku ignores unknown keys; existing `/api/state`
unchanged). The Roku reads `catalog.json` (rebuilt from per‑item sidecars by
`scripts/media-reindex.py`) sliced into these shapes. Same omit‑not‑null rule: `gps`,
`place`, `uploader` etc. are **omitted** when unknown.

```jsonc
// GET /api/media?type=trips  — the browse rows (one per collection)
{ "schemaVersion": 1, "type": "trips",
  "collections": [
    { "id": "2026-07-04--jasper-icefields", "kind": "trip",   // kind: trip|bucket
      "title": "Jasper & the Icefields",
      "poster": "/media/trips/2026-07-04--jasper-icefields/thumbs/cover.jpg",
      "itemCount": 42, "videoCount": 8, "photoCount": 34,
      "dateStart": "2026-07-04", "dateEnd": "2026-07-07",
      "place": "Jasper, AB",                                   // omitted if unknown
      "detailUrl": "/api/collections/2026-07-04--jasper-icefields" } ] }

// GET /api/collections/<id>  — items within a collection (404 if unknown id)
{ "schemaVersion": 1, "id": "...", "kind": "trip", "title": "...",
  "dateStart": "...", "dateEnd": "...", "place": "...",
  "items": [
    { "id": "abc123", "type": "video", "title": "Athabasca Falls",
      "url": "/media/trips/.../videos/2026-07-04T14-22-31--abc123.mp4",
      "poster": "/media/trips/.../thumbs/2026-07-04T14-22-31--abc123.jpg",
      "durationSec": 47, "codec": "h264", "width": 1920, "height": 1080,
      "captureDatetime": "2026-07-04T14:22:31-06:00",
      "gps": { "lat": 52.66, "lon": -117.88 }, "uploader": "Aunt Robin" } ] }

// GET /api/photos[?collection=<id>]  — flat slideshow list (newest first)
{ "schemaVersion": 1,
  "photos": [ { "id": "def456", "url": "/media/.../photos/...jpg",
                "poster": "/media/.../thumbs/...jpg",
                "captureDatetime": "2026-07-04T15:01:10-06:00",
                "gps": { "lat": 52.66, "lon": -117.88 },
                "collectionId": "2026-07-04--jasper-icefields", "title": "..." } ] }

// POST /api/upload  (multipart/form-data: files[], uploader?, trip?, tripTitle?, lat?, lon?)
{ "schemaVersion": 1, "ok": true, "batchId": "2026-07-04T19-40-02--7c3f",
  "accepted": [ { "name": "IMG_0421.HEIC", "bytes": 3145728 } ],
  "rejected": [ { "name": "notes.txt", "reason": "unsupported_type" } ] }
```

- **URLs are root‑relative** (`/media/<path>`, `/api/collections/<id>`); the Roku prepends
  its `SALLY_API_BASE` host. `/media/<path>` resolves under `MEDIA_ROOT` (traversal rejected)
  and honors `Range` (mandatory for Roku MP4 seeking — returns `206` + `Content-Range` +
  `Accept-Ranges: bytes`).
- **MP4s are faststart + CFR**, H.264 High@L4.2 ≤1080p (the gold‑standard encode profile).
- `captureDatetime` is ISO‑8601 with offset; the Roku formats its own display label.
- The studio `type=movies|tv|kids` catalog is reserved — currently returns empty `collections`.

## Trip + fuel entry (C2 / C3)

Driver/navigator mobile forms, cloned from the guest‑upload pattern. Both write atomic JSON
read‑models on the **Pi SD card** (never the failing HDD); `/api/state` folds them into the
`trip` and `fuel` sections above.

```jsonc
// POST /api/trip  (form-data) — create/replace the active trip, or end it.
//   create: title (req), destName?, aboard?(comma list), dateStart?, dateEnd?
//           pin?=1 + lat?/lon?  → pin current GPS as destination (offline fallback)
//   end:    end=1               → clears activeTripId
//   destName is geocoded via Nominatim over LTE; on miss/offline the trip saves without a
//   pin (camping geofence stays inactive until coords resolve).
{ "schemaVersion": 1, "ok": true, "id": "jasper-run",
  "dest": { "lat": 52.87, "lon": -118.08 }, "destReason": null }

// GET /api/trip — the store (the form shows the active trip + offers "End trip")
{ "schemaVersion": 1, "activeTripId": "jasper-run", "trips": { "jasper-run": { ... } } }

// POST /api/fuel-log  (form-data: odo?, litres(req), price?)  — native numeric keypad
//   datetime (GPS UTC → server fallback) + lat/lon are stamped server-side.
{ "schemaVersion": 1, "ok": true,
  "entry": { "ts": 1751650000, "datetime": "2026-07-04T18:00:00Z", "odo_km": 142400.0,
             "litres": 88.0, "price_per_l": 1.55, "total_cost": 136.4,
             "l_100km": 22.0, "mpg_imp": 12.8, "lat": 52.87, "lon": -118.08 } }
```

- A freshly‑created trip appears in `GET /api/media?type=trips` **immediately** as a zero‑item
  collection (merged from the trip store), so the upload form's trip picker lists it before any
  reindex. `scripts/media-reindex.py` later reconciles the same store (SD wins over the legacy
  per‑collection HDD `trips/<cid>/trip.json`).

## Versioning policy
Additive fields are non‑breaking (Roku ignores unknown keys). Renames/removals/semantic
changes bump `schemaVersion` and the Roku `sallyCacheV`. The contract test in the channel
(`tests/contract/`) validates live `/api/state` against this schema fixture. The `mode` enum
gained `camping` additively — the Roku tolerates unknown mode strings (routes nowhere), so this
did not bump `schemaVersion`.
