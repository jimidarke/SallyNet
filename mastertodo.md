# SallyNet — Master TODO

Planning surface for the next big push: making the **SallyNet Roku channel the single
interface for everything** (the built-in Roku Media Player is never used), with **Media
split into Trips / Movies / TV Shows**, all played in-app. Lay out every part here first;
execute as a batch once the plan is settled.

**Legend:** `[ ]` todo · `[~]` in progress · `[x]` done · `[?]` open question/decision

---

## 0. Where we are (done — v0.4.0, 2026-06-26)

- [x] Phase 0 shell (Splash / Home / Drive, `/api/state` poll) — live on Camperoku.
- [x] Phase 1 home media: encode pipeline + ingest + geotag + `sally-api` (`/api/media?type=trips`,
      `/api/collections/<id>`, `/api/photos`, `/media` Range, `/api/qr.png`, upload) + Roku
      Media (rows-as-trips), `VodPlayer`, PhotoGallery, QrScreen. Deployed + verified.
- [x] GPS breadcrumb logger + nightly idle-prio encode timer on the Pi (won't fight RetroPie).
- Notes: media disk **replaced by a Crucial BX500 1TB SSD** (ext4) on 2026-06-27 — the failing exFAT HDD is gone; staying on **Pi Buster** for now (N100 is the real upgrade later); catalog + tracks live on the Pi SD card, independent of the media disk.

---

## Locked decisions (this push)

- **SallyNet is the only Roku interface** — built-in Roku Media Player retired from use; SallyNet stays the boot/default channel.
- **MiniDLNA left running, untouched** (other devices / fallback). The Roku channel plays via `sally-api` `/media`, not DLNA.
- **Media = one page, tab strip:** `Trips | Movies | TV Shows`. D-pad up to tabs, left/right to switch.
- **Uploads always go to Trips** (the home pipeline). Movies/TV are curated from owned files.
- **TV `.mkv` → re-encode from source later**, not remuxed on Sally. Indexer emits a worklist; originals are kept off-Sally; re-encoded `.mp4`s drop into a studio inbox. Movies (already mp4) work day one.
- **Posters/metadata:** fetch online (LTE) + cache to the SSD for offline; hand-editable overrides; frame-grab fallback.

---

## A. Media-as-everything redesign

### A1 — Backend: serve the studio library — DONE (2026-07-04)
- [x] Broadened via a **second root**, not by repointing `MEDIA_ROOT`: `STUDIO_ROOT` (`/mnt/usb`) handles `movies/…` and `tv/…`; `MEDIA_ROOT` (`home/library`) is untouched — repointing one root would have broken every existing Trips URL (they're stored relative to `home/library`). Confirmed live paths have **no `media/` prefix** — it's `/mnt/usb/movies/…` and `/mnt/usb/tv/…` directly (every "media/movies", "media/tv" mention below was wrong, now fixed).
- [x] Re-verified: Range (206) + traversal guard (403/404) both tested against the new dispatch, movies + trips.
- [x] `STUDIO_ROOT` + `MOVIES_JSON` added to `sallyconf.py` + `sally-media.conf` (env-overridable, same idiom as everything else there).

### A2 — Backend: studio indexer — movies + TV DONE (2026-07-04, v0.7.0)
- [x] New `scripts/media-index-studio.py` + `services/sally-api/studio_index.py` — scans `movies/<Title (Year)>/…`:
  - [x] Movies: one item per folder with a real video file (title/year from folder name; folders with no file yet are silently skipped — the library is mid-transfer, ~24 of 178 folders populated so far).
  - [x] TV: dir = show; `scan_tv` parses `SxxExx` (+ loose `NxN`) → show / season / episode; only playable `.mp4`/`.m4v` episodes enter the model (pending hidden for free). **DONE.**
- [x] `movies.json` + `tv.json` emitted (Pi SD, like `catalog.json`).
- [ ] Re-encode worklist (A6) — not started (moot until real non-mp4 TV sources exist; almost all current folders are empty placeholders, not un-encoded originals).
- [x] Overrides file (`configs/media/studio-overrides.json`) — built; git-tracked + deploy-installed "only if absent" (same precedent as `sally-media.conf`). Movies + shows + episodes maps; match overrides (tmdbId/title/year) at fetch, presentation (genres/kidSafe/poster/still) at build.

### A3 — Backend: API endpoints — movies + TV DONE (2026-07-04, v0.7.0)
- [x] `GET /api/media?type=movies` → `{collections:[{id,kind,title,itemCount,detailUrl}]}` (categories, not flat items — see A5 below for why).
- [x] `GET /api/media?type=tv` → show-card rows (`tv-*` namespaced ids); new `GET /api/show/<id>` returns seasons/episodes. Empty until TV content is on disk.
- [x] `GET /api/collections/<id>` extended to also resolve movie category ids (tries movies, then falls through to the trips catalog/store, same layering as trip stubs).
- [x] Documented in `subsystems/media/api-contract.md`.

### A4 — Backend: poster/metadata fetch (online → cached) — DONE for Movies (2026-07-04, v0.7.0)
- [x] `services/sally-api/studio_art.py` + `scripts/media-fetch-art.py` (TMDB v3 `api_key`, stdlib-`urllib`). Match by title+year (±1 yr guard + confidence); genres via `/genre/movie/list`; posters `w342` → `STUDIO_ROOT/.art/<id>.jpg`, served by a one-line `_STUDIO_DIRS += ".art"`.
- [x] Frame-grab fallback (ffmpeg, the `media-encode-video.sh` recipe) when offline / unmatched.
- [x] Schedule: nightly `media-index-studio.timer` (incremental — ~0 TMDB calls after first populate) + on-demand `media-fetch-art.py --force/--refresh`. Creds via the `TILE_API_KEY` idiom (`.env.tmdb` → `sally-api.env`).
- [ ] TV show/episode art via TMDB `tv` endpoints — not yet; TV art is override-driven meanwhile (consumed from the same `.art` index shape, zero further change).

### A5 — Roku: UI restructure — movies + tab strip + full TV DONE (2026-07-04, v0.7.0)
> **Nav reorg (v0.7.0):** Trips pulled OUT of the Media page into its own Home **Trips** tile (new `TripsScreen`, photos+videos); Media is now a **Movies | TV** tab strip **defaulting to Movies**. Supersedes the "default tab always Trips" decision below.
- [x] `MediaScreen` reworked into a tab strip (Trips / Movies / TV Shows); D-pad Up focuses the tab row (real SceneGraph focus moves to an inert `tabRow` Group so the active RowList genuinely releases input), Left/Right switches tabs, Down/OK returns to the pane. **Default tab is always Trips** (resolved — not "remember last").
- [x] **Trips** pane = existing rows-as-trips (unchanged, regression-verified live).
- [x] **Movies** pane = **reuses the same RowList + MediaCard mechanism as Trips** (curated rows = categories), not a MarkupGrid/`MoviesGrid` — resolved as **curated rows**, not a flat grid. Phase 1 ships one row ("All Movies"); more rows (Kids & Family, genre) can be added later purely server-side, zero Roku changes needed.
- [x] **TV Shows** pane = show-card rows → `EpisodesScreen` (rows-as-seasons drill-in, fed by new `ShowDetailTask` from `/api/show/<id>`); empty-safe.
  - [x] Per-episode resume bookmark — fell out "for free" (composite episode id = `contentid`, so `resume:<id>` is unique per episode).
  - [x] **Autoplay next episode** — new `VodPlayer` `queue`/`queueIndex` + `advanceToNext` (whole show as a cross-season queue; single-decoder-safe stop→reload on the same Video node).
  - Pending-episode display: **hide entirely** — `scan_tv` only emits playable `.mp4`/`.m4v` episodes, so this is automatic.
- [x] New `StudioListTask` (sibling of `MediaListTask`, shares extracted `source/Http.brs`) for `type=movies`; registry cold-start cache **not** added (matches the existing gap — `SN_REG_MEDIA_CATALOG`/`PHOTO_CATALOG` consts have been dead/unused since Trips shipped too).
- [x] Kid-safe: **resolved as badge/flag only**, no lock/PIN mode. MediaCard has a dormant badge (shows once `kidSafe` data exists, Phase 4). This makes the frozen contract's reserved `type=kids` value unnecessary — struck from `api-contract.md`, `kidSafe` is just an item flag now.

### A6 — Re-encode worklist (the bridge to your owned TV) — not started
- [ ] Indexer generates `docs/studio-reencode-worklist.md`: every non-mp4 file, by show/season, with counts — the list to re-encode **from the high-quality originals (kept off-Sally)**. One encode profile for everything (movies/trips/TV) — the existing gold-standard `media-encode-video.sh`, unchanged, no per-source quality tiers.
- [ ] Studio inbox (e.g. `/mnt/usb/_inbox/` — no `media/` prefix) where re-encoded `.mp4`s land.
- [ ] Runs through the existing gold-standard pipeline (on a beefier box / the N100), not on the Pi.

### Build order for A
1. ~~A1 + A2(movies) + A3(movies) + A5(Movies pane)~~ **DONE 2026-07-04.**
2. ~~A5 tab strip restructure~~ **DONE 2026-07-04.**
3. ~~A2(tv) + A3(tv) + A5(TV drill-in + autoplay-next)~~ **DONE 2026-07-04 (v0.7.0).** Empty-safe UI; A6 re-encode worklist still pending (moot until real non-mp4 TV sources exist).
4. ~~A4 posters (online fetch + cache + overrides)~~ **DONE 2026-07-04 (v0.7.0)** for Movies (TMDB match/genre/poster + frame-grab fallback + overrides). TV show-art is override-driven until the art pipeline gains TMDB `tv` endpoints (plugs into the same `.art` slot, zero further change).
5. **Deploy to hardware — DONE (2026-07-04).** Pi `sally-api` + media pipeline deployed and active on campingpi; `GET /api/media?type=movies` live (24 items, "All Movies" category), `type=tv` live (empty — no non-placeholder show folders yet, expected). Roku channel sideloaded to Camperoku (`npm run deploy` ok). **Live end-to-end verify (remote-in-hand check of the new tab strip / TV drill-in / autoplay-next) still wants a real session at the TV.**

### Open questions for A — all resolved 2026-07-04
- [x] Default tab: **always Trips.**
- [x] Pending episodes: **hide entirely** (not grey-disable).
- [x] Kid-safe: **flag/badge only** (not a lock/mode) — see A5.
- [x] Movies: **curated rows** (categories), not a flat grid — see A5.
- [x] Curation overrides: git-tracked, deploy-installed (see A2). TMDB key: already in `.env.tmdb` (see A4). Art dir: `STUDIO_ROOT/.art`.
- [~] **VERIFY photos pipeline** — confirmed mechanics (upload → `inbox/<batch>/` + `upload.json` → nightly 02:00 ingest → `library/<route>/photos/` → `/api/photos` + Media→Trips; not instant). **Storage unblocked 2026-06-27** — the failing HDD that broke the first real ingest was replaced with the SSD (HDD item below). Re-verify the happy path with a real upload now. **Side note:** the upload form defaulted `trip` to `unsorted`, contradicting the "uploads always go to Trips" locked decision — fix the default so uploads land in `trips/`.

---

## B. Broader SallyNet roadmap (the "moonshot" master plan)

> **Canonical detail:** the full 7-phase plan — locked decisions, frozen `/api/*` contract +
> `/api/state` schema, sensor BOM, ffmpeg/UCI recipes — lives in
> `~/.claude/plans/plan-out-the-lot-robust-globe.md` (the moonshot session). This list is the
> tracker; that file is the spec. (It also cites a 16-domain / ~300-source research artifact.)

**Gates (physical, by you — block the noted phases):**
- [?] **12V under-voltage diagnosis** — converter-output vs battery-post delta under load; `vcgencmd get_throttled` must read `0x0` before trusting P2 power data. *(gates P2 power)*
- [?] **Tank-material photo** (plastic vs steel) — gates probe-reuse vs SeeLevel, and Mopeka vs Senso4s propane. *(gates P2 tanks / P7 propane)*

**Phases:**
- [x] **P0** — shell (Splash/Home/Drive + `/api/state` poll).
- [~] **P1** — Media: home trips + photos + upload done; **Movies/TV = Workstream A**.
- [ ] **P2** — Sensors + Camp/Systems (Pi-hosted, gated on power): Mosquitto + ~150-line collector + SQLite; ESP32 nodes — **belly** (tanks: CD4051 + reused 1980s probes), **cabin** (env BME280/AHT20/DS18B20 + IMU MPU-9250 for leveling/heading), **house** (12V INA226/shunt). Offline **`/api/map.png`** render + **`/api/level.png`** bubble + compass. Camp + Systems screens. Cabin **fuel logger** (node-door → `/api/fuel-log`). **Node fleet contract + catalog: `subsystems/telemetry/esp-fleet.md` (tracked in C4).**
- [ ] **P3** — N100 migration + Cameras: move services + the media SSD to the N100 (modern OS, current ffmpeg → HEVC, drops Buster workarounds); Pi → pure RetroPie; go2rtc USB capture → MJPEG rear-view + HLS dashcam; Cameras screen + Drive rear-view PIP (auto on `drive.reverse`).
- [ ] **P4** — Audio: RF headphones (movie lip-sync) + BETS-1 FM (music); audio-status strip.
- [x] **P5** — QR photos *(landed early as part of P1 home media)*.
- [ ] **P6** — Router WiFi-as-WAN: travelmate + mwan3 over UCI/SSH; RT5370 USB WiFi; Network panel.
- [ ] **P7** — Propane + shore AC + polish: Mopeka + LP leak detector (read-only); isolated PZEM-004T; optional HA/Grafana on N100.
- [ ] **Netflix / YouTube** launch tiles on Home. NOT in-channel ECP (Roku prohibits a channel
  issuing ECP commands; no in-channel launch API). Route via `sally-api`: channel POSTs
  `/api/launch?app=netflix` → Pi (external controller) ECP `/launch/<id>` to the Roku
  (id from `request.remote_addr`). Launch-only first pass; deep-link `contentId` deferred.
  Plan: `subsystems/media/netflix-youtube-launch-tiles-plan.md`.
- [x] **HDD replaced with SSD (2026-06-27)** — the failing Seagate exFAT HDD was swapped for a **Crucial BX500 1TB SSD** (ext4, `/mnt/usb` by UUID, `nofail`). Media **not migrated — re-encode from source** (catalog reset 0/0); the user's movies/TV were preserved; SD read-models untouched; Pi now boots at `get_throttled=0x0`. History: `subsystems/media/hdd-failure-2026-06-26.md`.
- [ ] **Channel tests** — `package.json` test:unit/test:smoke/contract scripts are stubs (no files yet); build them out.

---

## C. New ideas (2026-06-26 brain dump)

### C0 — Quick wins (small; do alongside A)
- [ ] **Wire phone-shared upload GPS into geotagging (or drop it)** — `POST /api/upload`
  captures the browser's `lat`/`lon` (guest checks "Attach my phone's location" on `/upload`)
  into `upload.json`, but `media-ingest.sh`'s `process_batch` only reads `trip`/`tripTitle`/
  `uploader` from that manifest — the phone GPS is never passed to `media-extract-meta.py`'s
  `--set`. Today only embedded EXIF GPS and GPX-track correlation actually geotag items
  (`media-extract-meta.py`'s locked fallback chain: embedded -> track -> omit); the
  phone-shared coordinate is dead data. Decide: wire it in as a lowest-priority fallback
  (after embedded, after track correlation) for photos with no GPS at all, or remove the
  checkbox if it's redundant with EXIF on virtually all phone photos.
- [ ] **Speed deadband** — round speeds below ~1 km/h to 0 so GPS jitter (e.g. 0.3 km/h while parked) never reads as moving or flips mode. Apply in `sally-api` gps normalize (`gpsd_client`/`_derive_mode`) and/or Roku display.
- [ ] **Time format everywhere** — `h:mm AM/PM`, localized to the **GPS-derived timezone**, with a zone abbreviation badge (**MT / PT / CT …**) that updates as we cross zones. Needs offline tz-from-GPS (coarse longitude/boundary lookup, no internet). Replace `snClockHM`/`snClockHMS` + any timestamp rendering.
- [x] **Weather tile (Home top-right)** — fill the empty top-right of the Home hub with **local weather based on GPS** (fetch over LTE, cache to the SSD for dead zones). Small current-conditions card. *(CODED — Environment Canada current conditions: `weather-refresh.py` worker + `ec_weather.py` + `weather.{service,timer}` → `weather.json`, folded into `/api/state.weather`; `WeatherCard` on HomeHub with EC iconCode glyphs. Not yet deployed to hardware.)*

### C1 — Home page push-to-QR — DONE (2026-07-04, v0.7.0)
- [x] Pressing **★ (the `options`/star key) on Home** shows the upload QR on demand (`MainScene.onKeyEvent` → re-parentable `QrScreen` route with `qrParent="home"`), so guests get the QR without navigating into Trips/Photos. (Chose the star key over the ECP `/input` deep-link idea.)

### C2 — Driver / navigator dashboard (trip entry) — BUILT (2026-06-27)
- [x] A **navigator entry pad** (`/trip` mobile page → `POST /api/trip`) to enter **trip parameters**: destination, trip name, who came (names), start/end dates. Destination geocoded via Nominatim (LTE), with a **"pin current GPS"** offline fallback. Active trip stored on SD (`/var/lib/sally/trips.json`).
- [x] Feeds **three** things now: (a) **auto-creates the Trip collection** (merged into `/api/media?type=trips` instantly, reconciled by `media-reindex.py`); (b) the **Drive screen** (To / ETA / Aboard) + new **Camp screen**; (c) the **`camping` geofence** (4th GPS mode — `at destination` vs generic `parked`).
- ETA is **OSRM road-routing** (`scripts/trip-eta-refresh.py` 60 s timer → `route.json` cache), straight-line `km_to_dest` as the offline fallback.
- [x] **Ambient map / navigation — BUILT (2026-06-27)**: server-composited `/api/map.png` (Thunderforest basemap + breadcrumb trail + waypoint pins + Overpass POIs + heading arrow + status strip), Roku `MapScreen`, phone `/waypoints` editor, `waypoint-eta`/`poi-refresh`/`map-preseed` jobs, offline tile cache + low-zoom gap-fill. Resolved its own spec: `subsystems/gps/map-navigation-brainstorm.md`.

### C3 — Fuel / gas-mileage log — BUILT (2026-06-27)
- [x] **Driver entry pad** (`/fuel` mobile page, native numeric keypad → `POST /api/fuel-log`) records **odometer, litres, $/litre**; datetime (GPS UTC) + GPS location auto-stamped.
- [x] Computes **L/100km + mpg(imp) + total cost**; dual sink `fuel-log.json` (SD) + `docs/fuel-log.md`; running average surfaced in `/api/state.fuel` + the Drive-screen footer. ESP32 door keypad+OLED stays the future hardware path (same endpoint).

### C4 — Telemetry sensors (ESP32 fleet) — PLAN CONSOLIDATED (2026-06-27)
> **Canonical:** the full fleet contract (firmware / MQTT / broker / power / secrets) + node catalog
> + topic→state map + build order live in `subsystems/telemetry/esp-fleet.md`. This is the tracker.
- [ ] **Node 0 — cabin-env (`sally-01`):** DHT22 config already written (`configs/telemetry/cabin-temp-humidity.yaml`); **deploy first** (no new HW). Expands to BME280 + DS18B20 (engine bay) + MPU-9250 (leveling/heading).
- [ ] **Collector** — `scripts/telemetry-collector.py` (MQTT → SQLite read-model) + systemd unit; sibling to the durable `telemetry-logger.sh`. Folds latest values into `/api/state.{env,tanks,power,level,systems}`.
- [ ] **Node 1 — env satellites** (bunk, …): clone of node 0; temp/humidity "in a few spots".
- [ ] **Node 2 — fireside-portable (`camp`):** temp+humidity only, 18650 + deep-sleep (battery-optimized); ESP-NOW→gateway is the noted upgrade path if WiFi range/battery disappoints. *(new 2026-06-27)*
- [ ] **Node 3 — tanks:** CD4051 + reused 1980s probes → fresh/grey/black %; **fresh-fill = level trend**. *Gated on the tank-material photo.*
- [ ] **Node 4 — power:** Tier-1 INA228 shunt (SoC) + Tier-2 hall clamps → **also pump/furnace run-state + shore presence**. *Gated on the 12V wiring diagnosis.*
- [ ] **Node 5 — fuel-keypad:** 4×4 keypad + OLED @ driver door → `POST /api/fuel-log` (web `/fuel` already built).
- [ ] **Node 6 — backseat-eta:** button + OLED, "are we there yet?" → GET `/api/state` ETA / km-to-dest. Glass consumer, no contract change. *(new 2026-06-27 — scoped to ETA only)*
- [ ] **Node 7 — city-water switch (optional):** inline pressure switch → `systems.city_water`.
- [ ] **Contract:** add additive `systems {pump,furnace,city_water}` block to `api-contract.md` (omit-not-null, no `schemaVersion` bump). `env` stays flat for the tile; collector keeps per-node detail in SQLite.
- [?] **Schema lock:** every node publishes under `sally/telemetry/<area>/…` — retire the `sally/<subsystem>/…` drift (anything outside `sally/telemetry/+` falls out of the logger's subscription).

### C5 — Cameras (future version — some data already gathered)
- [ ] Build on the gathered data for a later version. Ideas to exploit: backup-cam **live tile + GPS overlay** (driving mode, see B/P3), **auto rear-view on reverse** (`/api/state drive.reverse` already exists), **dashcam recording**, **motion snapshots**. Park as a future phase.

---

## D. Behaviour — always-on dashboard (fixes)

- [ ] **Never sleep / quit / screensaver / return to Home on idle.** **Investigated 2026-07-04: there is no BrightScript/manifest API to suppress the system screensaver** (checked against the RokuAppDev reference — only `screensaver_*` manifest keys exist, for registering your own *animated* screensaver, not disabling the OS one). Delta Cam's precedent (`DELTA-CAM-CASE-STUDY.md` "Auto-launch on power-on") solves the equivalent problem entirely through **device configuration, not code**: install **AutoLaunch** (free, Channel Store) on Camperoku, set it as the active screensaver configured to relaunch SallyNet, and shorten Settings → Theme → Screensavers → Wait time. This is a manual on-device setup task for whoever has the remote — not a channel code change.
- [x] **BUG: Drive bounces back to Home.** ~~Opening Drive shows it for a moment, then `applyMode`... yanks it back~~ **FIXED 2026-07-04**: `MainScene.brs` now tracks `m.manualRoute` — `true` when `go()` is called (manual nav: HomeHub taps, Back, deep-link args), `false` when `goAuto()` is called (mode-triggered switches: splash exit, `applyMode`). `applyMode` still freely *promotes* into Drive/Camp when a mode starts, but is blocked from *demoting* to Home if the current screen has `m.manualRoute = true`. Lint-clean (`npm run lint`); deployed to Camperoku already (as part of verifying the fix boots clean, before realizing a live show was on screen — see always-on item's caution above and [[feedback_no_unapproved_roku_actions]] in memory). Full behavioral confirmation (nav to Drive while parked, confirm it sticks) still wants a live remote-in-hand check next time someone's at the TV, since ECP control is disabled on this device and can't be scripted remotely.

---

## Master execution
Settle the `[?]` items above, then execute workstream A in the listed build order
(Movies first — it works with zero re-encoding). Update statuses here as we go.
