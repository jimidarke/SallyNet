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

### A1 — Backend: serve the studio library
- [ ] Broaden the `/media/<path>` Range root from `home/library` to the **media-disk top** (`/mnt/usb`) so `media/movies/…`, `media/tv/…`, and `home/library/…` all stream through the one handler. Keep the traversal sandbox (reject `..`, resolve under root).
- [ ] Re-verify Range (206) + traversal guard against the broadened root.
- [ ] Config: add `STUDIO_ROOT` / adjust `MEDIA_ROOT` in `sallyconf.py` (env-overridable for N100).

### A2 — Backend: studio indexer
- [ ] New `scripts/media-index-studio.py` — scan `media/movies` + `media/tv`:
  - Movies: one item per `.mp4` (title from filename; `container=mp4`, playable).
  - TV: dir = show; parse `SxxExx` (and loose patterns) → show / season / episode; record source container (`mkv` ⇒ pending re-encode).
- [ ] Emit `movies.json` / `tv.json` read-models (on the Pi SD, like `catalog.json`).
- [ ] Emit the **re-encode worklist** (see A6).
- [ ] Merge a hand-editable **overrides** file (`configs/media/studio-overrides.json`): title, year, hidden, kidSafe, posterOverride, per file/show.

### A3 — Backend: API endpoints (additive to the frozen v1 contract)
- [ ] `GET /api/media?type=movies` → `{items:[{id,title,url,poster,year,kidSafe,...}]}`.
- [ ] `GET /api/media?type=tv` → `{collections:[{id=show,title,poster,seasons,episodeCount,...}]}`.
- [ ] `GET /api/collections/<show>` → episodes grouped by season (reuse the existing shape; add `season`/`episode`/`pending`).
- [ ] Document all of the above in `subsystems/media/api-contract.md` (additive).

### A4 — Backend: poster/metadata fetch (online → cached)
- [ ] New `scripts/media-fetch-art.py` — when LTE is up, look up posters + title/year (TMDB), cache art to `/mnt/usb/media/.art/`; write matches into the catalogs.
- [ ] `[?]` TMDB API key — where stored (gitignored `.env`?) and rate/locale settings.
- [ ] Frame-grab fallback (ffmpeg) when offline / unmatched.
- [ ] Opportunistic schedule (systemd timer when online?) vs. manual run — decide.

### A5 — Roku: UI restructure
- [ ] Rework `MediaScreen` into a **category tab strip** (Trips / Movies / TV Shows); remember last tab; D-pad up → tabs.
- [ ] **Trips** pane = existing rows-as-trips (unchanged).
- [ ] **Movies** pane = `MoviesGrid` (MarkupGrid of posters) → `VodPlayer`. (Optional later: rows by Kids/Family/All.)
- [ ] **TV Shows** pane = shows grid → `Episodes` screen (seasons + episodes) → `VodPlayer`.
  - [ ] Per-episode resume bookmark (registry, keyed on contentid — `VodPlayer` already does this).
  - [ ] **Autoplay next episode** within a show (cancellable countdown).
  - [ ] **Pending greyout** for not-yet-re-encoded `.mkv` episodes (visible but not selectable).
- [ ] New `MediaListTask` fetches (or a sibling task) for `type=movies` / `type=tv`; registry cache for cold-start.
- [ ] Confirm SallyNet stays the boot/default channel; built-in player never invoked.

### A6 — Re-encode worklist (the bridge to your owned TV)
- [ ] Indexer generates `docs/studio-reencode-worklist.md` (or `.json`): every non-mp4 file, by show/season, with counts — the list to re-encode **from the high-quality originals (kept off-Sally)**.
- [ ] Define a **studio inbox** (e.g. `/mnt/usb/media/_inbox/`) where re-encoded `.mp4`s land → indexer picks them up → episode flips from "pending" to playable.
- [ ] Re-encode runs through the **existing gold-standard pipeline** (on a beefier box / the N100), not on the Pi.

### Build order for A
1. **A1 + A2(movies) + A3(movies) + A5(Movies pane)** — Movies end-to-end, usable immediately (zero re-encode).
2. **A5 tab strip** restructure (Trips / Movies / TV Shows).
3. **A2(tv) + A3(tv) + A5(TV drill-in)** + **A6 worklist** — TV structure live; episodes fill in as re-encoded.
4. **A4 posters** (online fetch + cache + overrides).

### Open questions for A
- [~] **VERIFY photos pipeline** — confirmed mechanics (upload → `inbox/<batch>/` + `upload.json` → nightly 02:00 ingest → `library/<route>/photos/` → `/api/photos` + Media→Trips; not instant). **Storage unblocked 2026-06-27** — the failing HDD that broke the first real ingest was replaced with the SSD (HDD item below). Re-verify the happy path with a real upload now. **Side note:** the upload form defaulted `trip` to `unsorted`, contradicting the "uploads always go to Trips" locked decision — fix the default so uploads land in `trips/`.
- [?] Default tab (Trips? last-used?).
- [?] Pending episodes: grey-disable (planned) vs. hide entirely.
- [?] Kid-safe: just a flag/badge, or an actual "kids mode" filter/lock?
- [?] Movies: flat poster grid vs. curated rows (genre/kids/all).
- [?] Where curation overrides + TMDB key live; art dir path.

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
- [ ] **Speed deadband** — round speeds below ~1 km/h to 0 so GPS jitter (e.g. 0.3 km/h while parked) never reads as moving or flips mode. Apply in `sally-api` gps normalize (`gpsd_client`/`_derive_mode`) and/or Roku display.
- [ ] **Time format everywhere** — `h:mm AM/PM`, localized to the **GPS-derived timezone**, with a zone abbreviation badge (**MT / PT / CT …**) that updates as we cross zones. Needs offline tz-from-GPS (coarse longitude/boundary lookup, no internet). Replace `snClockHM`/`snClockHMS` + any timestamp rendering.
- [ ] **Weather tile (Home top-right)** — fill the empty top-right of the Home hub with **local weather based on GPS** (fetch over LTE, cache to the SSD for dead zones). Small current-conditions card.

### C1 — Home page push-to-QR
- [ ] Push a command from the main screen / external trigger to **show the upload QR on demand** (ECP `/input` deep-link or an Info-button surface), so guests can be handed the QR without navigating into Photos.

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

- [ ] **Never sleep / quit / screensaver / return to Home on idle.** The dashboard must hold its current screen indefinitely with no input — suppress the Roku screensaver (keep-alive activity ping / exempt the channel), never auto-exit, keep SallyNet the foreground + boot/default channel.
- [ ] **BUG: Drive bounces back to Home.** Opening Drive shows it for a moment, then `applyMode` (modeController in `MainScene.brs`) yanks it back: Drive is treated as a "passive" auto-switchable screen, and while parked the mode is `at_home`/`parked` → `routeForMode` → `home`. **Fix:** auto-routing should only **promote into Drive when driving starts**, and **never demote a user-selected screen** back to Home. Make manual navigation sticky (don't auto-route away from a screen the user chose until they leave it). Same root rule as the always-on item above.

---

## Master execution
Settle the `[?]` items above, then execute workstream A in the listed build order
(Movies first — it works with zero re-encoding). Update statuses here as we go.
