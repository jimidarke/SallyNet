# Phone web UIs — forms, endpoints, payloads

Authoritative: `subsystems/media/api-contract.md`. Implementation:
`services/sally-api/app.py` (HTML forms are inline `_UPLOAD_HTML` / `_TRIP_HTML` /
`_FUEL_HTML`). Base `http://192.168.2.216:8090`; schema v1; omit-not-null.

## Guest upload — `GET /upload`, `POST /api/upload`

- **Page** lists the trip picker (from `/api/media?type=trips`), an optional uploader
  name, a file picker, and an optional "share my phone GPS" consent box.
- **`POST /api/upload`** — `multipart/form-data`: `files[]`, `uploader?`, `trip?`,
  `tripTitle?`, `lat?`, `lon?`. Files land in `/mnt/usb/home/inbox/<batchId>/` with an
  `upload.json` manifest.
- **Response:**
  ```jsonc
  { "schemaVersion": 1, "ok": true, "batchId": "2026-07-04T19-40-02--7c3f",
    "accepted": [ { "name": "IMG_0421.HEIC", "bytes": 3145728 } ],
    "rejected": [ { "name": "notes.txt", "reason": "unsupported_type" } ] }
  ```
- Accepted types: photos `jpg jpeg png heic heif webp tif tiff bmp gif`; video
  `mp4 mov m4v mkv avi 3gp 3g2 webm mts m2ts wmv flv`. `UPLOAD_MAX_BYTES` = 8 GB/request.
- **QR:** `GET /api/qr.png` encodes `LAN_BASE_URL` (`…/upload`). Kept as the LAN IP, not
  `.local`, because Android mDNS is flaky and guests may be on cellular.

## Mileage / fuel logger — `GET /fuel`, `POST /api/fuel-log`

- **Page** uses a native numeric keypad for one-handed entry at the pump.
- **`POST /api/fuel-log`** — `odo?`, `litres` (required), `price?`. The server stamps
  `datetime` (GPS UTC → server clock fallback) and `lat`/`lon` server-side.
- **Response:**
  ```jsonc
  { "schemaVersion": 1, "ok": true,
    "entry": { "ts": 1751650000, "datetime": "2026-07-04T18:00:00Z", "odo_km": 142400.0,
               "litres": 88.0, "price_per_l": 1.55, "total_cost": 136.4,
               "l_100km": 22.0, "mpg_imp": 12.8, "lat": 52.87, "lon": -118.08 } }
  ```
- **Dual sink:** `/var/lib/sally/fuel-log.json` (machine read-model, SD) + `docs/fuel-log.md`
  (human-readable mirror; on the Pi `/opt/sally/sally-api/docs/fuel-log.md`). `l_100km` is
  per-tank (litres ÷ odometer delta to the previous fill); `avg_l_100km` is the running
  mean. Surfaces in `state.fuel = { last:{…}, avg_l_100km, fills }`.

## Trip entry — `GET /trip`, `GET·POST /api/trip`

- **`POST /api/trip`** create/replace: `title` (req), `destName?`, `aboard?` (comma list),
  `dateStart?`, `dateEnd?`, or `pin=1`+`lat`/`lon` to pin current GPS as destination
  (offline fallback). End the trip: `end=1`. `destName` is geocoded via Nominatim over
  LTE; on a miss the trip saves without a pin (camping geofence stays inactive).
- **Response:** `{ schemaVersion:1, ok:true, id, dest:{lat,lon}, destReason }`.
- **`GET /api/trip`** → `{ activeTripId, trips:{…} }` (the page shows the active trip +
  an "End trip" button).
- **Side effects:** a new trip appears in `GET /api/media?type=trips` immediately as a
  zero-item collection (so the upload picker lists it before any reindex), and drives
  `state.trip` (km_to_dest haversine always present; OSRM `eta`/`roadKm` when cached) and
  the Drive-screen ETA. Store: `/var/lib/sally/trips.json` (SD, atomic — source of truth).

## Waypoints — `GET /waypoints`, `GET·POST /api/waypoints`

Phone editor for trip pins; `POST` adds/deletes/toggles a waypoint. Stored in
`/var/lib/sally/waypoints.json`; `waypoint-eta-refresh.py` computes road-km/ETA to the
next unvisited one and auto-marks it visited on arrival. Drawn on `/api/map.png`.

## Browser map — `GET /map`, `GET /api/map.png`

`/map` is a troubleshooting/off-TV browser viewer (manual refresh + zoom/layer toggles)
of the same `/api/map.png` the Roku shows. Params (all optional, server owns center+zoom):
`w`,`h` canvas; `z=auto` (speed band) or forced `10–15`; `layers` CSV of
`base,trail,poi,waypoints,labels,status`; `v` cache-buster (Roku sets it to `state.ts`).

## `/api/state` (what the Roku polls)

The heartbeat. Key sections: `gps` (live), `drive.km_from_home`, `trip` (only when
active), `fuel` (only once a fill is logged), `mode`
(`driving|camping|parked|at_home|unknown`), `system.throttled` (under-voltage canary).
Sensor blocks `power/tanks/env/level/systems` are reserved and **omitted** until the ESP
fleet fills them. Full schema + field notes: `subsystems/media/api-contract.md`.
