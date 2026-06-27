# Roku channel UX (Camperoku)

The TV experience. The Roku is **glass**: every screen polls the `:8090` API over HTTP
and renders — it never speaks MQTT, gpsd, or SQLite. That separation is what keeps the
Pi → N100 migration a one-line `SALLY_API_BASE` change. Source:
`roku-channel/channel/components/` + `roku-channel/CLAUDE.md`. For BrightScript/SceneGraph
*engineering*, use the `RokuAppDev` skill.

Device: Roku Premiere 3920CA, OS 15.2.4, `192.168.2.227` (`10.66.12.227` over the tunnel),
ECP on `:8060`. Dev mode currently ON; SallyNet channel sideloaded.

## State router — `MainScene`

Polls `/api/state` (~5 s) and routes by `mode`:

- Splash → **HomeHub** on launch.
- Auto-route to **Drive** when `mode=driving` (speed ≥ 10 km/h) and to **Camp** when
  stopped at an active trip's destination. The Roku applies the real hysteresis
  (`modeController`), not the server (which only sends an instantaneous hint).
- Manual navigation is **sticky** — a screen the user chose is not auto-demoted.
- Never sleeps; screensaver suppressed; this is the boot/default channel.

## Screens (`components/screens/`)

| Screen | What it shows | Reads |
|---|---|---|
| **HomeHub** | mascot hero (520×287) + nav tiles + a live status ribbon | `/api/state` |
| **MapScreen** | fullscreen ambient map; dual-poster ping-pong, cache-busted by `state.ts` | `/api/map.png?w=&h=&v=` |
| **MediaScreen** | RowList, one row per trip collection; MediaCard posters + metadata | `/api/media?type=trips`, `/api/collections/<id>` |
| **VodPlayer** | MP4 playback with HTTP Range seeking, trick-play, resume bookmarks | `/media/<path>` |
| **PhotoGallery** | slideshow with capture date / place / uploader overlay | `/api/photos` |
| **QrScreen** | the upload QR for guests to scan | `/api/qr.png` |

## Rendering patterns worth knowing

- **Ambient map** is a single server-composited PNG — the Roku does no map math, just
  shows the image and ping-pongs two `Poster` nodes so swaps don't flash. The server owns
  center (live GPS) and speed-based zoom; the Roku just sets `v=<state.ts>` to force a
  re-fetch when the snapshot changes.
- **MP4 seeking requires Range** — `/media/<path>` returns `206` + `Content-Range` +
  `Accept-Ranges: bytes`; encodes are faststart H.264 High@L4.2 ≤1080p CFR.
- **Omit-not-null** — a missing `/api/state` key reads as `invalid` and the Roku hides
  that widget; a literal `null` would crash a SceneGraph `assocarray` field, so the API
  never emits one. Keep that invariant if you touch the API.

## Contract test

The channel has a contract test (`roku-channel/.../tests/contract/`) that validates live
`/api/state` against the schema fixture. Additive API fields are safe (the Roku ignores
unknown keys); renames/removals must bump `schemaVersion` **and** the Roku `sallyCacheV`.
