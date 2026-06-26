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
| `/api/map.png?z=&w=&h=` | GET | P2 | offline‑rendered PNG centered on current GPS |
| `/api/media?type=trips` | GET | **live (P1)** | home‑media collections (trips/drone/memories/unsorted) |
| `/api/media?type=movies\|tv\|kids` | GET | reserved | studio library — empty `collections` until built |
| `/api/collections/<id>` | GET | **live (P1)** | items (videos+photos) within one collection |
| `/media/<path>` | GET | **live (P1)** | faststart H.264 MP4 / JPEG, **HTTP Range** (206) |
| `/api/level.png` | GET | P2 | pre‑rendered leveling bubble PNG |
| `/api/photos[?collection=<id>]` | GET | **live (P5)** | flat slideshow list |
| `/api/qr.png` | GET | **live (P5)** | QR encoding the LAN upload URL guests scan |
| `/api/upload` · `/upload` | POST · GET | **live (P5)** | guest upload endpoint · mobile upload page |
| `/api/fuel-log` | POST | P2 | ESP32 door logger → appends `docs/fuel-log.md` + SQLite |

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
  "mode": "driving|parked|at_home|unknown",// instantaneous HINT; Roku applies hysteresis
  "gps": {                                 // LIVE from gpsd (P0)
    "fix": true, "mode": 3,                // mode: 0/1 none, 2 = 2D, 3 = 3D
    "lat": 53.546100, "lon": -113.493800,
    "speed_kmh": 0.1,                      // "heading" present only when moving (omitted when stationary)
    "alt_m": 669.2, "sats": 12, "sats_visible": 15, "hdop": 0.65,
    "time": "2026-06-26T06:55:18.000Z"     // gps time (UTC)
  },
  "drive": { "km_from_home": 0.0, "reverse": false },  // odo_km/trip_km omitted until available
  "alerts": [],                            // [{ kind, sev, text, ts }]
  "system": { "host": "campingpi", "uptime_s": 0, "throttled": "0x0" }
  // --- omitted until populated (never sent as null) ---
  //   "power":  { batt_v, batt_a, soc_pct, tte_h, shore, mains_w }   (P2)
  //   "tanks":  { fresh_pct, grey_pct, black_pct, propane_pct }      (P2)
  //   "env":    { in_c, out_c, engine_c, humidity, pressure_hpa }    (P2)
  //   "level":  { pitch_deg, roll_deg, level_ok }                    (P2)
  //   "cameras":{ rearview, dashcam }                                (P3)
  //   "audio":  { source, fm_on }                                    (P4)
}
```

**Field notes**
- `gps.speed_kmh` derived from gpsd TPV `speed` (m/s × 3.6). `heading` from TPV `track`
  (degrees true); omitted when stationary or no fix.
- `drive.km_from_home` is haversine to the saved home anchor (default Edmonton
  `53.5461,-113.4938`, radius 150 m). Configurable via `SALLY_HOME_LAT/LON/RADIUS_M`.
- `mode` is an instantaneous hint (`driving` if speed ≥ 8 km/h; `at_home` if within the home
  radius; else `parked`). The Roku `modeController` owns the real hysteresis (8 km/h ×5 s /
  <3 km/h ×3 min).
- `system.throttled` is `vcgencmd get_throttled` — the under‑voltage canary surfaced on the
  Systems screen.
- Sensor blocks (`power`/`tanks`/`env`/`level`/`cameras`/`audio`) are **omitted** until their
  phase fills them — never emitted as `null`.

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

## Versioning policy
Additive fields are non‑breaking (Roku ignores unknown keys). Renames/removals/semantic
changes bump `schemaVersion` and the Roku `sallyCacheV`. The contract test in the channel
(`tests/contract/`) validates live `/api/state` against this schema fixture.
