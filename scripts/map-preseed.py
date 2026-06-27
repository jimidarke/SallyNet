#!/usr/bin/env python3
"""map-preseed.py — pre-cache the tile pyramid for a bbox (known dead zones / before a trip).

Run on home wifi (or any good uplink). Caches every tile in [zmin, zmax] over a bbox into the
same TILE_CACHE_DIR that sally-api reads, so a planned route renders offline later. Reuses
tiles.fetch_tile (cache-first), so it's idempotent and a re-run only fetches what's still missing.

Polite + honest: sequential with a short delay, logs progress and a final tally, and REFUSES a
pyramid larger than PRESEED_MAX_TILES — printing the estimate first — so a silent cap is never
mistaken for full coverage. Mind your tile provider's monthly quota for big corridors.

Usage:
  map-preseed.py <lat1> <lon1> <lat2> <lon2> [zmin] [zmax]
  e.g. map-preseed.py 52.0 -118.5 53.6 -116.0 8 14   # Jasper / Icefields corridor

Env: SALLY_API_DIR (default /opt/sally/sally-api), PRESEED_DELAY_S, PRESEED_MAX_TILES, plus the
sally-api tile config (TILE_API_KEY, TILE_CACHE_DIR, TILE_URL_TEMPLATE).
"""
import os
import sys
import time

sys.path.insert(0, os.environ.get("SALLY_API_DIR", "/opt/sally/sally-api"))
import sallyconf as cfg          # noqa: E402
import tiles                     # noqa: E402

DELAY_S = float(os.environ.get("PRESEED_DELAY_S", "0.05"))
MAX_TILES = int(os.environ.get("PRESEED_MAX_TILES", "60000"))


def _xy(lat, lon, z):
    px, py = tiles.world_px(lat, lon, z)
    return int(px // tiles.TILE), int(py // tiles.TILE)


def _ranges(south, west, north, east, z):
    xmin, ymin = _xy(north, west, z)   # NW corner -> min x, min y
    xmax, ymax = _xy(south, east, z)   # SE corner -> max x, max y
    return xmin, xmax, ymin, ymax


def _estimate(south, west, north, east, zmin, zmax):
    total = 0
    for z in range(zmin, zmax + 1):
        xmin, xmax, ymin, ymax = _ranges(south, west, north, east, z)
        total += (xmax - xmin + 1) * (ymax - ymin + 1)
    return total


def main(argv):
    if len(argv) < 5:
        print(__doc__)
        return 2
    a, b, c, d = (float(argv[1]), float(argv[2]), float(argv[3]), float(argv[4]))
    south, north = min(a, c), max(a, c)
    west, east = min(b, d), max(b, d)
    zmin = int(argv[5]) if len(argv) > 5 else 8
    zmax = int(argv[6]) if len(argv) > 6 else 14

    if "{key}" in cfg.TILE_URL_TEMPLATE and not cfg.TILE_API_KEY:
        print("no TILE_API_KEY set — preseed cannot fetch tiles. Put it in .env and retry.")
        return 1

    total = _estimate(south, west, north, east, zmin, zmax)
    print("pyramid z%d-%d over [%.4f,%.4f]..[%.4f,%.4f] = %d tiles"
          % (zmin, zmax, south, west, north, east, total))
    if total > MAX_TILES:
        print("REFUSING: %d tiles > PRESEED_MAX_TILES (%d). Narrow the bbox or lower zmax. "
              "NOTHING cached." % (total, MAX_TILES))
        return 1

    done = ok = 0
    for z in range(zmin, zmax + 1):
        xmin, xmax, ymin, ymax = _ranges(south, west, north, east, z)
        for x in range(xmin, xmax + 1):
            for y in range(ymin, ymax + 1):
                done += 1
                if tiles.fetch_tile(z, x, y) is not None:
                    ok += 1
                time.sleep(DELAY_S)
        print("  z%d: %d/%d cached so far" % (z, ok, done))
    print("preseed done: %d/%d tiles cached (%d failed) into %s"
          % (ok, done, done - ok, cfg.TILE_CACHE_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
