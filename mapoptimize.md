# Map tile fetch — caching + throttle/error-handling followup

**Status:** captured 2026-06-27, right after the ambient-map build (P1–P5). The map works; this
doc is about **hardening the tile-fetch layer against a slow/throttling tile provider** and
recording how the caching behaves. One fix (concurrent fetch) already landed this session; the
rest is **proposed, not yet built**.

Owner files: `services/sally-api/tiles.py` (fetch + cache + basemap), `services/sally-api/mapgen.py`
(status strip), `services/sally-api/sallyconf.py` (config). Design context:
`subsystems/gps/map-navigation-brainstorm.md`.

> **⚠️ Vendor-compliance correction (2026-06-27).** An earlier note here implied Thunderforest's
> free tier permits the caching/pre-seed this design uses. It does **not**: Thunderforest's *free*
> Hobby plan (and the $125 Solo plan) **forbid server-side disk caching + bulk pre-download** — those
> require the Small Business tier ($255/mo) or a **custom arrangement** (which the owner is pursuing).
> MapTiler and Stadia forbid server-side caching too. The genuinely-free + offline + compliant path
> is **self-rendered tiles from OSM/ODbL data** (PMTiles — the N100-era upgrade). Until the
> paid/custom Thunderforest plan lands, the throttle hardening below (now **shipped**) is what keeps
> request rates polite and well-behaved.

---

## Why this exists — the incident

While testing, Thunderforest (the raster tile provider) started tarpitting us after a burst of a
few hundred tile fetches. Symptoms:

- Raw `curl` straight to `tile.thunderforest.com` (bypassing all our code): one tile took **5.7 s**,
  others **timed out at 8 s**. So it was the *provider*, not our code/WSL/compositor.
- A **cold-area** render (`/api/map.png` for a fresh place) needs ~40 uncached tiles. Sequentially
  that hung **40 s+**; the in-flight render held the single-flight render lock, so *nothing* else
  rendered either.
- Worse, the compositor **re-attempted the same failing tiles on the very next render** (every few
  seconds) — hammering an already-struggling provider.

Self-inflicted by heavy testing, BUT the same thing hits Sally for real on **first arrival in a new
area over a flaky/slow LTE link** — so it's worth smoothing out.

---

## Current caching — three layers, three lifetimes

| Layer | Where | Lifetime | Notes |
|---|---|---|---|
| **Tile cache** (basemap PNGs) | `/mnt/usb/home/maptiles/{z}/{x}/{y}.png` — **SSD** | **Forever** — no TTL, no eviction. Survives reboot/restart. | One PNG per slippy tile, written on first fetch. Re-visiting = instant, zero network (the offline strategy). |
| **Rendered-PNG cache** (composed frame) | process RAM (`mapgen._last`) | ~3 s moving / ~20 s parked; **gone on restart** | Single frame, keyed shape+content. The poll throttle. |
| **POI / waypoints / route JSON** | `/var/lib/sally/*.json` — **SD** | Durable, crash-safe (atomic writes) | Lets POIs/waypoints/countdown keep working offline. |

**Tile-cache specifics (the important one):**
- **Best-effort R/W** — a read/write error is swallowed → a disk error or unmount just means that
  tile doesn't cache (silently re-fetched next time), never crashes a render. (See `tiles._cache_read` /
  `tiles._cache_write`.)
- **It's on the media SSD** (the Crucial BX500 at `/mnt/usb`, ext4). "Persists forever" holds as long
  as the SSD stays mounted and healthy. The durable copies are the SD read-models, not the tiles.
- **If `/mnt/usb` is unmounted**, caching silently disables → every render goes live → permanent
  slowness. A real failure mode worth detecting + surfacing (see followups).
- **Unbounded growth** — no size cap / LRU. Fine at 500 GB for years; note it anyway.
- **Never refreshes** — a tile cached today is served indefinitely even if OSM changes. Acceptable
  for a basemap; a stale tile is cleared only by deleting the file (or a future `?fresh=1`).

---

## Already done (2026-06-27)

- ✅ **Concurrent tile fetch.** `tiles.basemap()` now fetches a viewport's uncached tiles with a
  `ThreadPoolExecutor` (max 8 workers) instead of one-by-one. Cuts worst-case first-render ~8×
  (sequential 40×latency → a few parallel batches). Cached/healthy path unchanged (still ~0.27 s).
  42 unit tests still green. Worker count could become an env key (`TILE_FETCH_WORKERS`).

---

## Throttle / error handling — ✅ SHIPPED 2026-06-27 (was "proposed")

All five landed in `tiles.py` (+ the `throttled` chip in `mapgen._map_chip_state`), TDD'd in
`test_tiles.ThrottleTests` / `test_mapgen.MapChipTests`. Pure, time-injected (`_now`/`_net`) so the
breaker/negative-cache decisions are unit-tested off the Pi. Highest-value first; all in `tiles.py`
unless noted.

| # | Mechanism | What it does | Sketch |
|---|---|---|---|
| **1** | **Negative cache** (per-tile failure backoff) | A failed/timed-out tile is marked "don't retry for ~60 s," so the render skips straight to gap-fill instead of re-hitting a known-bad tile every frame. **Biggest win** — stops the hammering *and* makes degraded renders fast. | module dict `_tile_fail_until[(z,x,y)] = now + cfg.TILE_FAIL_COOLDOWN_S`; `fetch_tile` returns None immediately (no network) while cooled down. |
| **2** | **Circuit breaker** (global) | If N fetch failures land in a short window → trip for ~45 s: serve cache + gap-fill only, no network at all. Turns "40 timeouts = 30 s hang" into "~3 fails → trip → instant frame." Protects provider *and* latency. | module counters `_fails`, `_breaker_until`; `fetch_tile` early-returns cache-or-None while tripped; a single probe re-closes it. |
| **3** | **Honor 429 / Retry-After** | If the provider says "back off," actually do — read `Retry-After`, feed the breaker cooldown. Clean throttle compliance. | catch `HTTPError` 429 in `fetch_tile`, set `_breaker_until = now + retry_after`. |
| **4** | **Tighter, configurable timeout** | 6 s → ~4 s, env-tunable, so even without the breaker a slow tile gives up to gap-fill faster (bounded by slowest tile under concurrency). | `cfg.TILE_TIMEOUT_S` (default 4); use in `urlopen(timeout=...)`. |
| **5** | **Surface it** | Status strip shows `throttled` / `offline` (already shows `gaps` / `approx`). So a stale basemap from a tripped breaker is obvious. | thread a `throttled` flag from `basemap` stats → `mapgen._draw_status` chip. |

**Net effect:** when the provider tantrums, you get a **fast gap-filled frame with a "throttled"
badge** instead of a 30 s hang, and the provider is left alone to recover. The happy path
(cached/healthy) is untouched.

**New `sallyconf.py` keys:** `TILE_TIMEOUT_S=4`, `TILE_FAIL_COOLDOWN_S=60`,
`TILE_BREAKER_FAILS=6`, `TILE_BREAKER_WINDOW_S=20`, `TILE_BREAKER_COOLDOWN_S=45`,
`TILE_FETCH_WORKERS=8` (all env-overridable, matching the existing pattern).

**Do NOT:** add per-tile retries (hammers harder — backoff is the opposite and correct); move the
tile cache to the SD (wear-sensitive; tiles are bulky + disposable — the media SSD is the right call
and best-effort writes already tolerate transient faults).

**Testing:** the breaker + negative-cache decisions are pure, time-based logic (inject `now`) — TDD
them exactly like `mapgen._reuse_cached` (`test_tiles.py`). Add an integration check: a `fetch` that
always fails/sleeps → assert the render returns fast, gap-fills, sets `throttled`, and does NOT keep
calling `fetch` for cooled-down tiles.

---

## Other followups / watch-items

- **Media-disk unmount detection.** If `/mnt/usb` isn't mounted, tile caching silently no-ops → every
  render is live → chronic slowness. Detect (cache dir missing/!writable) and surface a one-time
  warn + a status hint, so it's diagnosable instead of mysterious.
- **Cache size / hygiene.** Unbounded today (fine at 500 GB). If ever needed: an LRU prune or a
  `du` cap. Lower priority than the breaker.
- **Pre-seed is the real mitigation for planned routes** — `scripts/map-preseed.py <bbox> [zmin zmax]`
  on home wifi warms the corridor so there's no cold first-render in known dead zones. Bounded by
  `PRESEED_MAX_TILES`.
- **N100 migration.** The durable fix for offline + provider independence is a **Protomaps PMTiles**
  regional archive (vector→raster), swappable behind `tiles.fetch_tile()` — see the brainstorm's
  "Resolved → Tile source." That removes the per-tile network dependency entirely.

---

## The mapping interface (shipped 2026-06-27 — W1–W5)

Beyond the tile-fetch hardening above, the ambient map grew into a controllable, layered interface.
All additive to the frozen `/api` contract (no `schemaVersion` bump); all TDD'd in the `test_*.py`
suite. The PNG is generated **on demand** per `/api/map.png` request (the Roku polls; the server
single-flight-caches it), tuned for highway/city driving — not streamed.

- **Shared view-state (W1).** `/var/lib/sally/view-state.json` + `GET/POST /api/view` hold the active
  layer set. `/api/map.png` with no `?layers=` renders that shared state, so a toggle on the `/map`
  web page persists server-side and **every browser + the Roku glass converge** (zero Roku edits — it
  already sends no `layers`). `_shape_sig` keys on the layer set, so a change yields a fresh frame on
  the next poll with no manual cache bust.
- **GPS-loss overlay (W2).** An always-on red "GPS SIGNAL LOST" banner (amber "WAITING FOR GPS" if
  never fixed) baked on once a fix is missing past `SALLY_GPS_ALERT_AFTER_S` (20 s). The map **freezes
  at the last-known position** (never teleports home). A coarse 5 s `_alert_sig` bucket folds into the
  content sig so the banner/counter refresh promptly. Also surfaced on every Roku screen via
  `/api/state.alerts` (`gps_lost`) + a `nav` section. NOT a toggleable layer.
- **Background nav-tick (W3).** `scripts/nav-tick.py` — a `Type=simple` daemon (not a timer; a ~7 s
  timer would cold-start the interpreter ~12k×/day on the Pi 3B+) reads gpsd directly and maintains
  `nav-state.json` (fix-age + frozen last-known) so loss is detected even when nobody polls. Pure
  logic in `navstate.py`. Optional, **license-gated** tile pre-warm (`NAV_PREWARM`, OFF) — only when
  the tile plan permits proactive fetching.
- **Photo POIs (W4).** Past-trip geotagged photos surface as magenta camera pins near the current
  position. `media-reindex.py` piggybacks `photo-poi.json` off the catalog rebuild (no new timer); the
  `photos` layer declutters like POIs plus a hard `PHOTO_POI_MAX_KM` great-circle cull.
- **Favourites (W5).** A `favourite` flag on the existing `waypoints.json` — saved places (manual
  decimal lat/lon entry on `/waypoints`) drawn as gold stars, **excluded from the route** by a
  one-line filter in `select_next_waypoint` (covers both the map's "next" and the arrival
  auto-advance). `op=promote` turns a favourite into a route stop.

## Extensibility — satellite base (future)

The layer mechanism is open: a new layer is `ALL_LAYERS` + a `_draw_*` in `_compose` + a read-model.
Satellite was deferred, but the `baseSource` field in `view-state.json` reserves the hook. The
compliant choice is **EOX Sentinel-2 cloudless** (CC BY-NC-SA, non-commercial, ~10 m, attribution
required, caching/self-host permitted) wired behind `tiles.fetch_tile()` as a `street ⇄ satellite`
toggle on `/api/view`. (A hybrid sat+labels variant is a later step.)

## Verify
1. `python3 -m unittest test_tiles` — breaker/negative-cache unit tests green.
2. Simulate a slow/failing provider (monkeypatch `fetch_tile` to sleep/fail): a cold render returns
   in <~1 s with gap-fill + a `throttled` badge, and the provider isn't re-hit for cooled tiles.
3. On `campingpi`: after a real deploy, watch `journalctl -u sally-api` while requesting
   `/api/map.png` for a fresh area on a quiet link — confirm fast frames + recovery once tiles cache.
