---
name: sallynet-interfaces
description: >-
  How people actually USE SallyNet — the human-facing surface and the frozen
  :8090 API. Use for any user-interaction task: the phone web pages on SallyNet
  WiFi (the QR photo-upload page, the mileage/fuel logger, the trip-entry form,
  the waypoint editor, the browser map), the Roku channel screens guests see on
  the TV, how an uploaded photo travels to the screen, the /api contract itself,
  or the planned interactions — RF/amateur-radio voice, the ESP32 sensor/control
  nodes (cabin env, tanks, power, the driver-door fuel keypad, the back-seat "are
  we there yet?" button), and WLED lighting. Trigger on "how do guests add
  photos", "the fuel/mileage website", "log a fill-up", "set up a trip on the
  dashboard", "what screens are on the Roku", "the camper-to-camper radios", "the
  back-seat ETA button". For deploying or operating the Pi host, use
  sallynet-pi-ops; for the LAN, tunnel, or router, use sallynet-networking; for
  BrightScript/SceneGraph channel engineering, use RokuAppDev.
---

# SallyNet interfaces — how people use Sally

Sally's tech is for the family that camps in her. The user-facing surface is three
things: **phone web pages** served on SallyNet WiFi (upload, mileage, trips), the
**Roku channel** on the TV (glass that shows media + an ambient map), and a **growing
set of physical inputs** (ESP32 nodes, future RF radios). Everything funnels through
one frozen HTTP API on `:8090` so the Roku and the N100 migration stay simple.

This skill is a **thin index over the source of truth**. The frozen contract is
`subsystems/media/api-contract.md` — when you build or change anything user-facing,
read it first; this body orients you to what exists and where.

## The one API surface

Base URL `http://192.168.2.216:8090` (`campingpi` today; `10.66.12.216:8090` over the
tunnel; moves to the N100 at Phase 3 — a one-line `SALLY_API_BASE` change). **No auth**
(trusted LAN). Schema version `1`; unavailable fields are *omitted, never null*.

| Path | What the user gets |
|---|---|
| `/upload` · `POST /api/upload` | mobile photo/video upload page · the endpoint behind it |
| `/api/qr.png` | QR that encodes the `/upload` URL (shown on the Roku for guests to scan) |
| `/fuel` · `POST /api/fuel-log` | **mileage/fuel logger** page · logs a fill-up |
| `/trip` · `GET·POST /api/trip` | trip-entry page · create/end the active trip |
| `/waypoints` · `GET·POST /api/waypoints` | phone waypoint pin editor |
| `/map` · `/api/map.png` | browser map viewer · the server-composited map PNG |
| `/api/state` | the full snapshot the Roku polls (~5 s) — GPS, trip, fuel, mode |
| `/api/media?type=trips` · `/api/collections/<id>` · `/api/photos` | browse the home library |
| `/media/<path>` | the actual MP4/JPEG bytes (HTTP Range, for Roku playback) |

Per-page form fields, payloads, and responses:
[`references/web-uis.md`](references/web-uis.md).

## Phone web pages (on SallyNet WiFi)

- **Photo upload (`/upload`)** — a guest scans the QR on the Roku, lands on the mobile
  page, picks a trip + (optionally) shares phone GPS, and uploads. Files stream into
  `/mnt/usb/home/inbox/<batchId>/` for the pipeline. The QR encodes `LAN_BASE_URL`
  (`http://192.168.2.216:8090/upload`) — kept as the LAN IP because mDNS `.local` is
  flaky on Android and guests may be on cellular.
- **Mileage / fuel logger (`/fuel`)** — the "website for mileage." Driver enters
  odometer + litres + price on a native numeric keypad (one-handed at the pump). The
  server stamps time + GPS and computes **L/100 km and imperial mpg** and cost, writing
  both a machine read-model (`/var/lib/sally/fuel-log.json`) and a human-readable mirror
  (`docs/fuel-log.md`). Results surface in `state.fuel` (last fill, running `avg_l_100km`,
  fill count) on the Roku Systems tile. The 460 V8 is famously thirsty, so this is a
  real feature, not a toy.
- **Trip entry (`/trip`)** — name the trip, set a destination (geocoded via Nominatim
  over LTE, or pin current GPS offline), list who's aboard, set dates. Creating a trip
  drives the camping geofence + Drive-screen ETA and **instantly creates the matching
  upload bucket** so guests can file photos to it before any reindex.
- **Waypoints (`/waypoints`)** + **map viewer (`/map`)** — pin/edit trip waypoints;
  view the same composited map a browser instead of the TV.

## The Roku channel (Camperoku)

The Roku is **pure glass**: it polls `/api/state` and renders, never speaking MQTT,
gpsd, or SQLite. Screens (`roku-channel/channel/components/screens/`):

- **HomeHub** — mascot hero + nav tiles + a live status ribbon from `/api/state`.
- **MapScreen** — fullscreen ambient map; fetches `/api/map.png?...&v=<state.ts>` and
  ping-pongs two posters. Passive; the server owns center + speed-based zoom.
- **MediaScreen → VodPlayer** — browse trip collections, play library MP4s with Range
  seeking, trick-play, resume bookmarks.
- **PhotoGallery** — slideshow from `/api/photos` with capture date/place/uploader.
- **QrScreen** — shows `/api/qr.png` so guests can scan to upload.

`MainScene` is a state router: Splash → Home, auto-routing to Drive (speed ≥ 10 km/h)
or Camp (stopped at an active trip's destination), with manual navigation kept sticky.
Screen-by-screen behavior: [`references/roku-ux.md`](references/roku-ux.md). For Roku
*engineering* (BrightScript/SceneGraph patterns), use the `RokuAppDev` skill.

## Upload → screen (the round trip)

```
guest scans QR → /upload → /mnt/usb/home/inbox/<batch>/ → media-ingest.sh (nightly 02:00
or on demand) → dedup + encode (H.264 MP4 / JPEG + thumb) → library/<collection>/ +
per-item sidecar → media-reindex.py rebuilds catalog.json (SD) → Roku MediaScreen shows it
```

Currently the pipeline is built and verified end-to-end but **real uploads are blocked on
the failing media HDD** — see [`sallynet-pi-ops`](../sallynet-pi-ops/SKILL.md).

## What people will use next (planned)

Clearly not built yet — scope + status in
[`references/future-roadmap.md`](references/future-roadmap.md):

- **RF camper-to-camper voice = amateur radio.** Two vehicles in the BC backcountry talk
  via licensed 2 m/70 cm mobiles (Basic Qualification). **This is *not* the BETS-1 FM
  transmitter** — that's cabin-range music broadcast only, never the voice channel. Don't
  conflate them. (`subsystems/comms/amateur-radio-path.md`.)
- **ESP32 nodes** people touch: the **fuel keypad** at the driver door (4×4 + OLED →
  same `POST /api/fuel-log`) and the **back-seat ETA button** (press → GET `/api/state`
  → show km/ETA on an OLED). Sensor nodes (cabin env, tanks, power) need no user input.
  Catalog + contract: `subsystems/telemetry/esp-fleet.md`.
- **WLED ambient lighting** — soft LED zones (lounge, bunk) via ESP32 + WLED presets.
  (`subsystems/lighting/README.md`.)

## Canonical sources

- `subsystems/media/api-contract.md` — **the frozen `/api` surface (read first)**
- `services/sally-api/app.py` + `sallyconf.py` — the implementation + every default
- `roku-channel/channel/components/screens/*` + `roku-channel/CLAUDE.md`
- `subsystems/telemetry/esp-fleet.md` · `subsystems/comms/amateur-radio-path.md` ·
  `subsystems/lighting/README.md` · `docs/fuel-log.md`

## Related skills

- [`sallynet-pi-ops`](../sallynet-pi-ops/SKILL.md) — the host that serves all of this
- [`sallynet-networking`](../sallynet-networking/SKILL.md) — the LAN/tunnel it rides on
- `RokuAppDev` — BrightScript/SceneGraph engineering for the channel itself
