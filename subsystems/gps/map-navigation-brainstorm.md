# Ambient Map / Navigation Screen — Design Brainstorm

**Status:** Design captured 2026-06-27. Decided in a brainstorm pass; nothing built yet. This is
the richer version of the `/api/map.png` P2 stub described in
[`../media/api-contract.md`](../media/api-contract.md). Not yet phased into the Roku roadmap.

**Builds on what's already live:** GPS + gpsd serve a 3D fix exposed at `/api/state.gps`
(see [`README.md`](README.md)); the Pi already logs GPS breadcrumbs to `/var/lib/sally/tracks/`;
the guest-upload mobile page exists (P5). This feature composes those, it doesn't re-solve them.

## Goal

A **glanceable, self-updating "where are we" display** on Sally's TV — not turn-by-turn driving
nav (the driver isn't watching the TV). Passengers and people in camp can glance up and see
where Sally is, where she's been today, what's nearby, and how far to the next stop. Zero
interaction required.

## Decisions (this pass)

| Question | Decision | Why |
|---|---|---|
| Core purpose | **Ambient "where are we"** | Glanceable situational display, not a planning tool or trip-replay. Leans on already-solved live GPS. |
| Rendering architecture | **Server-composited PNG** (extend `/api/map.png`) | The Pi/N100 owns *all* cartography and bakes one flat PNG; Roku stays a dumb `Poster`. Simplest pipeline to build and maintain; barely touches the frozen API contract. |
| Map centering | **Sally-centered**, map pans under her | Heading arrow stays dead-center; the world scrolls beneath. |
| Zoom | **Speed-based auto-zoom**, server-side | Tight (z14–15) parked/slow in camp; wide (z10–11) at highway speed. Roku stays dumb — zoom is chosen from `gps.speed_kmh`. |
| On-TV interaction | **Purely flat — no selection** | The PNG *is* the experience. Nearby POI/waypoint labels (name + distance) are baked into the image. Only remote action is Back to exit. Truest to "ambient." |
| POI categories | **RV essentials · Fuel · Scenic & recreation** | "Survive the night," "don't run the 460 dry," and "why we came." Skipped the general supplies/services layer. |
| Waypoint source | **GPX/JSON file canonical + phone page editor** | File on the brains host is the source of truth (importable from anywhere); the existing upload mobile page grows a convenience editor that writes to it. |
| Uplink assumption | **Online-mostly via LTE, hours-offline resilient** | Not offline-first. Live-fetch + aggressive persistent cache, with graceful degradation when a stretch goes dark. |

## What it looks like

Full-screen map, **Sally pinned dead-center as a heading arrow** (rotates to `gps.heading` when
moving; neutral dot when parked). The map pans *under* her — she never leaves the center.
Auto-zoom by speed: tight in camp so you see the campground roads, wide on the highway so you
see the next town coming.

Baked into the composited PNG, in draw order:

1. **Basemap** — OSM raster tiles for the current center/zoom.
2. **Breadcrumb trail** — today's track as a colored polyline behind Sally (from
   `/var/lib/sally/tracks/`).
3. **POI glyphs** — RV-essential / fuel / scenic, each a distinct icon; only enabled categories;
   decluttered by zoom (fewer when zoomed out).
4. **Waypoint pins** — trip stops from the GPX file; the **active "next" waypoint** emphasized.
5. **Nearby labels** — name + distance baked next to the closest few POIs/waypoints (this is how
   "inspect a POI" survives in a flat-PNG world).
6. **Sally's arrow** — drawn last, always on top, always centered.
7. **Status strip** — a thin overlay (corner/bottom) with speed, elevation, "X km to **next
   waypoint**," and a fix/sat + uplink indicator so a stale map is obvious.

Self-updating with zero input. Roku polls and re-fetches the PNG as Sally moves; Back exits.

## Architecture: server composes, Roku displays

```
gpsd ──► /api/state.gps ─┐
tracks/ (breadcrumb) ────┤
GPX waypoints file ──────┤──►  map compositor (brains host)  ──►  /api/map.png  ──►  Roku Poster
POI cache (Overpass) ────┤        (basemap + layers → 1 PNG)
OSM tile cache (HDD) ────┘
```

- **`/api/map.png`** grows query params (additive, non-breaking): the existing `z`, `w`, `h` plus
  whatever the compositor needs (the server already knows center from live GPS, so the Roku may
  pass almost nothing). Speed-based zoom is chosen server-side, so `z` can become "auto" or be
  omitted. Schema/contract impact is minimal — the Roku is still just fetching a PNG.
- **Roku side** is a single screen showing one `Poster`, re-fetched on a movement/poll cadence.
  Honors the channel's decoder discipline (no video on this screen).

## Offline / tile strategy (online-mostly)

LTE gives mostly-available uplink; the design must survive multi-hour dead stretches without
*depending* on the modem.

- **Live-fetch + permanent cache.** The compositor pulls OSM tiles over LTE when there's signal
  and writes every tile to an HDD cache forever. Re-visiting anywhere already seen = free,
  instant, no uplink.
- **Optional trip pre-seed.** Before a leg with known dead zones (or any time on home wifi), a
  one-shot job caches the tile pyramid for a bbox around the planned route (zoom ~8–15). Nice to
  have, not load-bearing.
- **POI snapshot.** Overpass query per region cached to disk; refresh when online, keep serving
  the last snapshot when not.
- **Graceful degradation.** Missing tile + no uplink → render basemap from whatever's cached
  (low-zoom / blank fill for gaps). Sally's arrow, breadcrumb, POIs and waypoints still draw —
  they come from cached/local data, not live tiles. The uplink indicator in the status strip
  tells the viewer the basemap may be stale.

## Waypoints

- **Canonical:** a GPX (or simple JSON) file on the brains host — importable from anywhere,
  hand-editable, the single source of truth.
- **Editor:** the existing P5 guest-upload mobile page extends into a "trip" page so waypoints can
  be added/edited from a phone on the LAN; it writes back to the canonical file.
- The compositor reads the file each render; the **next** waypoint (by route order or proximity)
  is the one emphasized on the map and counted down in the status strip.

## Open questions / later

- **Tile source & licensing** — public OSM tile servers have usage policies; a self-hosted
  renderer or a tile provider with an offline-cache-friendly license may be needed for the
  pre-seed volume. Decide before heavy pre-seeding.
- **Movement-based re-fetch cadence** — how far Sally must move before the Roku pulls a fresh PNG
  (balance smoothness vs. LTE data vs. render load).
- **"Next waypoint" logic** — strictly route-ordered, or nearest-unvisited? Affects the countdown.
- **Pre-seed UX** — where the "cache this region" trigger lives (phone page button? CLI on the
  brains host?).
- **Phasing** — slot into the Roku roadmap (currently P0–P7); this is a natural P2 companion to
  the leveling/systems work since it shares `/api/*.png` server-render infrastructure.

## Next action

None scheduled — captured for later. When picked up: confirm a tile source that permits offline
caching at the volume needed, then spec the `/api/map.png` compositor params and the GPX file
schema before any Roku work.
