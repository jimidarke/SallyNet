# Media

**Pyle TV** (with built-in DVD) → manual HDMI input selector → {Roku, **AGPtek mini 1080** media player, (future) Pi}. The **9" TFT 4-camera backup-cam head unit** is separate today (its own display + RCA composite video out). Goal: collapse the Roku + AGPtek into a single unified experience by sideloading a custom Roku channel, AND route the backup-cam feed in too so the rear-view + side cameras can be watched on the big TV while driving.

## Status

- **Working:** Pyle TV + DVD, Roku (Netflix etc.), AGPtek mini 1080 for local files (downloaded movies, family photos). All hang off the manual HDMI switcher.
- **Working separately:** 4-camera 9" TFT backup-cam head — sits up front on its own screen; RCA composite output is currently unused.
- **Pain point:** Multiple devices, multiple remotes, multiple input selections, no continuity. Hard to hand to a kid or a guest. And the rear/side cameras are stuck on a tiny 9" screen.

## SallyNet channel — forked from HouseWall · **Phase 0 BUILT (2026-06-26)**

> The channel now lives in this monorepo at **`roku-channel/`** (app name
> **SallyNet**, matching the SSID). It's sideloaded + verified on Camperoku, polling
> `sally-api` `/api/state` and auto-routing Splash→Home→Drive. The **backend is `sally-api`
> on the Pi today** (`:8090`); it moves to the N100 at Phase 3 and the Roku just repoints
> `SALLY_API_BASE` (no channel code change). The fork notes below are the original plan,
> now largely realized.

Reference: sibling project `~/code/rokuApp` (HouseWall — production sideloaded SceneGraph channel, v0.5, devPassword: `HOUSEWALL_ROKU_DEV_PASSWORD` in the gitignored `.env`).

What to reuse:
- SceneGraph state router (MainScene)
- `LiveGroup` HLS / RTSP / MJPEG playback path with watchdog + exponential-backoff reconnect
- `GridGroup` 2×2 mosaic — repurpose as a scrolling thumbnail grid for movies / photos
- Overlay layer (PIP, text, weather, sensor zones)
- Registry caching pattern for fast cold-start

What changed (realized in Phase 1, below):
- Replaced `DiscoveryTask` (SSDP) with the fixed `sally-api` base URL (registry `apiBase`, default `http://192.168.2.216:8090`; overridable by ECP deep-link). No mDNS — the LAN IP is canonical.
- The backend exposes `GET /api/media?type=trips` + `GET /api/collections/<id>` + `GET /api/photos` + `GET /media/<path>` (HTTP Range) — on the **Pi today** (`sally-api`), migrating to the N100 at Phase 3 via a base-URL change.
- `VodPlayer` (adapted from `LiveGroup`) plays the `/media/<path>` MP4s instead of camera streams.
- Netflix / YouTube launch tiles — still to do. **Not** an in-channel ECP call (Roku disallows a
  channel issuing ECP commands on itself); routes through `sally-api` as an external controller
  instead. Design: `netflix-youtube-launch-tiles-plan.md`.

The channel code now lives **in this monorepo at `roku-channel/`** (consolidated 2026-06-26), not a separate repo. This folder holds the deploy/integration notes, the frozen `api-contract.md`, and UX notes.

## Phase 1 — Home media (trips / photos) · BUILT (2026-06-26)

Home-made content (camping trips, family memories, drone footage) is browsable + playable on the
Roku, served from the SSD via `sally-api`. Verified end-to-end on Camperoku (encode → catalog →
API → channel renders the catalog, no errors) — that pass used a **generated test image**
(artifacts since cleaned up, so the catalog currently reads 0/0).

> **✅ 2026-06-27 — storage blocker resolved.** The failing HDD was replaced with a **Crucial
> BX500 1 TB SSD** (ext4, `/mnt/usb` by UUID). The media library was **not migrated — it's being
> re-encoded from source** (catalog reset to 0/0); the user's movies/TV were preserved on the SSD.
> The happy path can be re-verified with a real upload now. History of the failure that prompted
> the swap: `hdd-failure-2026-06-26.md`.

**One optimal format, encode-once** (the "gold standard"): MP4 H.264 **High@L4.2**, ≤1080p
downscale-only (AR preserved, never upscaled), **CFR**, 2 s GOP, **CRF 20 + 12 Mbps cap**, AAC-LC
192k/48k, **`+faststart`** (moov first — mandatory for Roku progressive). Photos: ≤1080p sRGB JPEG
q85 + 480×270 thumbs. Codec is config-switchable (H.265 later on the N100). Confirmed by `ffprobe`
on a real Pi encode.

**Pipeline** (`scripts/` → deployed to `/opt/sally/media/` on the Pi):
- `media-ingest.sh` — filesystem-as-queue worker: atomic claim (`mv inbox→work`), sha256 dedup,
  route to trip/drone/unsorted, encode, publish atomically, write per-item sidecar, reindex,
  rollback-to-`failed/` on error. Modes `--once` (nightly) / `--watch` / `--batch` / `--reclaim`.
- `media-encode-video.sh` / `media-encode-photo.sh` — the gold-standard ffmpeg / ImageMagick encode
  (version-aware for the Pi's ffmpeg 4.1: `-vsync cfr`, `trunc(iw/2)*2` instead of `force_divisible_by`).
- `media-extract-meta.py` — exiftool + geotag chain (embedded GPS → GPX breadcrumb correlation → omit) → sidecar JSON.
- `media-track-logger.py` — gpsd → daily GPX breadcrumbs (SD card, `/var/lib/sally/tracks`).
- `media-reindex.py` — rebuild `catalog.json` read-model from sidecars (flock-guarded, on SD).
- `media-worker-remote.sh` — rsync-offload the heavy encoding to a laptop over SSH/WireGuard.
- systemd: `media-track-logger.service` (always-on) + `media-encode.timer` (02:00, `Nice=15` +
  idle CPU/IO so it never fights RetroPie). Config `configs/media/sally-media.conf`; deploy with
  `scripts/deploy-media-worker.sh`.

**Storage:** `/mnt/usb/home/{inbox,work,library/{trips,drone,memories,unsorted},originals,catalog/items,failed,logs}`.
Per-item sidecars (on the media SSD) are the source of truth; `catalog.json` + breadcrumbs live on
the Pi's SD card — crash-safe and independent of the media disk (see `docs/current-state.md`).

**Guest upload:** `GET /upload` (mobile page) + `POST /api/upload` stream files into `inbox/`; the
Roku **Photos → Info** shows `GET /api/qr.png`, so guests on SallyNet scan → upload from their phone
(camera roll, optional name/trip, optional phone-GPS). Files encode on the next nightly run.

**Roku screens:** Media (RowList, one row per trip) → `VodPlayer` (trick play + resume bookmark +
watchdog, EOF→back); Photos (two-poster slideshow + date/place overlay); `QrScreen`. Surface frozen
in `api-contract.md`.

## Studio library — Movies / TV (Workstream A) · CODED (2026-07-04, v0.7.0), not yet deployed

The user's **owned** movie/TV library (`/mnt/usb/{movies,tv}`, a second root — `STUDIO_ROOT` —
kept separate from `MEDIA_ROOT` so it can never touch Trips URLs) is now browsable the same way as
Trips, curated into rows instead of a flat grid.

- **Indexer:** `scripts/media-index-studio.py` + `services/sally-api/studio_index.py` scan
  `movies/<Title (Year)>/…` (one item per folder with a video file) and `tv/<Show (Year)>/Season
  NN/…` (parses `SxxExx`; only playable `.mp4`/`.m4v` episodes surface — pending transfers are
  hidden, never greyed). Emits `movies.json` / `tv.json` (Pi SD, alongside `catalog.json`).
- **Posters/metadata:** `services/sally-api/studio_art.py` + `scripts/media-fetch-art.py` match
  TMDB by title+year, fetch genre + poster art to `STUDIO_ROOT/.art/`, with an ffmpeg frame-grab
  fallback when offline/unmatched. TV art is override-driven until the pipeline gains TMDB `tv`
  endpoints. Hand-editable curation overrides: `configs/media/studio-overrides.json` (git-tracked,
  deploy-installed only-if-absent).
- **API:** `GET /api/media?type=movies|tv` (curated-row categories) + `GET /api/show/<id>`
  (seasons/episodes) — frozen in `api-contract.md`.
- **Roku:** `MediaScreen` is now a **Trips / Movies / TV Shows tab strip** (D-pad Up→tab row,
  Left/Right→switch, defaults to Trips); Movies reuses the Trips RowList/`MediaCard` mechanism;
  TV drills show→`EpisodesScreen` (rows-as-seasons, fed by `ShowDetailTask`) with per-episode
  resume + autoplay-next (`VodPlayer` queue/`advanceToNext`). New `StudioListTask` (sibling of
  `MediaListTask`).
- **Status:** coded + tested (backend unit tests + `bsc` lint clean) but **not deployed to
  hardware** — see "Next action" below.

## Bonus idea: live backup-cam → Roku with GPS map overlay (rolling)

This is the fun one. While driving, the big TV in the back of the camper shows:
- A live tile from the 4-camera backup-cam head (rear + side cameras)
- A GPS map overlay (route, speed, ETA) using the planned Pi GPS receiver
- Optional swap-to-fullscreen for any single camera

Implementation sketch:
1. Grab the **RCA composite out** of the 9" 4-cam head unit into a cheap **USB composite video capture dongle** plugged into the **mini-PC**
2. Mini-PC runs `ffmpeg` / `mediamtx` to publish the capture as an **MJPEG or low-latency HLS** stream on the LAN
3. SallyNet channel (forked from HouseWall — `LiveGroup` already speaks HLS/RTSP/MJPEG with watchdog + reconnect) consumes that stream
4. GPS overlay: mini-PC reads `gpsd` (see `subsystems/gps/`), composites a small map + speed/ETA panel into a separate stream, or sends GPS as JSON for the Roku to render natively in a SceneGraph layer (cheaper than re-encoding video)
5. Latency goal: <1.5s end-to-end — composite-capture + MJPEG over LAN is realistic here; HLS adds 4–10s and is too slow for "is the kid still behind me" use

Caveats:
- **Composite video out is interlaced 480i NTSC** — quality will be modest, but for situational rear-view it's fine
- The HouseWall `LiveGroup` reconnect/watchdog logic carries over directly — bumpy roads on RCA = signal loss is real
- The Roku and the backup cam are independent power domains; the Roku must boot fast enough to be useful — keep the channel as the boot-time default (Roku registry pattern, already in HouseWall)

## Roadmap

1. ✅ Forked rokuApp; consolidated into `roku-channel/`; rebranded **SallyNet** (sunset palette + mascot).
2. ✅ Media HTTP service stood up on the **Pi** (`sally-api` `/api/media` + `/media`) — moves to the N100 at Phase 3 (`subsystems/compute/`).
3. ✅ Built the home-media VOD + photo path (Media RowList, `VodPlayer`, PhotoGallery) — no camera-overlay cruft.
4. ✅ First sideload to Camperoku — verified live (polls `/api/state`, auto-routes Splash→Home→Drive).
5. ✅ **Studio library + Netflix-style nav (v0.7.0):** Home split into **Media** (Movies/TV) + **Trips**; Movies TMDB genre/poster rows + Continue Watching; **full TV** (shows→episodes, per-episode resume, autoplay-next); ★-on-Home upload QR. *Coded + tested (178 backend + `bsc` lint); not yet deployed to hardware.*
6. Add deep-link tile for Netflix / YouTube (separate `POST /api/launch` ECP design — see `netflix-youtube-launch-tiles-plan.md`).
7. **Driving mode** — composite-capture the backup-cam head into the mini-PC → LAN stream → Roku channel `LiveGroup` tile + GPS overlay.
8. Retire (or relegate) the AGPtek mini 1080 now that the SallyNet channel handles local files.

## Next action

The Netflix-style overhaul (v0.7.0) is **coded + tested** — Home Media/Trips split, Movies TMDB
genre/poster rows + Continue Watching, full TV (shows→episodes with per-episode resume +
autoplay-next), and the ★-on-Home upload QR. **Next: deploy + verify on hardware** — push `sally-api`
+ the pipeline to campingpi (`deploy-sally-api.sh` provisions the TMDB key from `.env.tmdb`), run
`media-fetch-art.py` over LTE to populate posters, sideload the channel to Camperoku, and walk the
flows (upload photo+video → Trips; Movies posters + rows; ★→QR; seed one TV show → episodes →
resume + autoplay-next). Then load real movie/TV content onto `/mnt/usb/{movies,tv}`, and Phase 2
(Camp/Systems sensors via MQTT).
