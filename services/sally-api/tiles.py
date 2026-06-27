"""tiles.py — Web-Mercator slippy-tile math + a best-effort tile cache/fetcher.

The pure functions (world_px / project / tiles_for_viewport / speed_to_zoom) take no config
and touch nothing external, so they're unit-tested off the Pi (test_tiles.py). basemap()
stitches the viewport's tiles onto one canvas, gap-filling whatever it can't fetch, so a cold
cache in an LTE dead zone degrades gracefully instead of failing.

Tiles come from a raster provider (cfg.TILE_URL_TEMPLATE, default Thunderforest Outdoors) and are
cached forever on the media disk. The OSM public tile server is deliberately NOT used — its usage policy
forbids the caching/pre-seed this design relies on. NB: Thunderforest's free Hobby tier forbids it
too (Small Business+ / custom plan required); the cache-forever design assumes that arrangement,
and the negative-cache + circuit breaker below keep request rates polite in the meantime.
"""
import io
import math
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

import sallyconf as cfg

TILE = 256
ZOOM_MIN = 10
ZOOM_MAX = 15
GAP_RGB = (232, 226, 211)  # muted parchment fill for missing tiles (matches the channel theme)


# --- pure math (no config / no I/O — fully unit-tested) ----------------------------------

def world_px(lat, lon, z):
    """Lat/lon -> global pixel coords in the zoom-z 256px tile pyramid (floats)."""
    scale = float(2 ** z) * TILE
    x = (lon + 180.0) / 360.0 * scale
    lat_rad = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * scale
    return (x, y)


def project(lat, lon, center, z, w, h):
    """Lat/lon -> canvas pixel for a w*h viewport centred on `center` (=(lat, lon))."""
    cx, cy = world_px(center[0], center[1], z)
    px, py = world_px(lat, lon, z)
    return (w / 2.0 + (px - cx), h / 2.0 + (py - cy))


def tiles_for_viewport(center, z, w, h):
    """Tiles needed to fill a w*h viewport centred on `center`.

    Returns [(x, y, sx, sy)]: tile index x (wrapped to [0, 2^z)), tile index y (may fall
    outside range at extreme latitudes — the caller gap-fills), and the float canvas offset
    (sx, sy) where the tile's top-left is pasted (may be negative / off-canvas).
    """
    n = 2 ** z
    cx, cy = world_px(center[0], center[1], z)
    left = cx - w / 2.0
    top = cy - h / 2.0
    tx0 = int(math.floor(left / TILE))
    ty0 = int(math.floor(top / TILE))
    tx1 = int(math.floor((left + w - 1) / TILE))
    ty1 = int(math.floor((top + h - 1) / TILE))
    out = []
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            out.append((tx % n, ty, tx * TILE - left, ty * TILE - top))
    return out


def speed_to_zoom(speed_kmh, has_fix=True):
    """Speed (km/h) -> integer zoom band: tight parked/in-camp, wide on the highway."""
    if not has_fix or speed_kmh is None:
        return ZOOM_MAX
    s = speed_kmh
    if s <= 8:
        z = 15
    elif s < 30:
        z = 14
    elif s < 50:
        z = 13
    elif s < 70:
        z = 12
    elif s < 95:
        z = 11
    else:
        z = 10
    return max(ZOOM_MIN, min(ZOOM_MAX, z))


# --- throttle state: negative cache + global circuit breaker -----------------------------
# Module-global, time-injected so the decisions are pure/testable (like mapgen._reuse_cached).
# A failed tile is "cooled" so the next render skips straight to gap-fill instead of re-hitting
# a known-bad tile every frame; the global breaker trips after a burst of failures (or a 429)
# and serves cache-only for a cooldown, then lets a single probe re-close it.

_neg = {}                    # (z, x, y) -> negative-cache-until epoch
_fails = []                  # recent failure timestamps within the breaker window
_breaker = {"until": 0.0}    # breaker (and 429) open until this epoch


def reset_throttle_state():
    """Clear the negative cache + breaker (tests, or a manual breaker reset)."""
    _neg.clear()
    _fails[:] = []
    _breaker["until"] = 0.0


def is_throttled(now):
    """True while the global breaker is open: serve cache + gap-fill only, no network."""
    return _breaker["until"] > now


def note_throttle(now, retry_after):
    """A provider 429: honor its Retry-After when given, else back off for our cooldown."""
    ra = float(retry_after or 0)
    _breaker["until"] = now + (ra if ra > 0 else cfg.TILE_BREAKER_COOLDOWN_S)


def _tile_cooled(z, x, y, now):
    return _neg.get((z, x, y), 0.0) > now


def _note_tile_failure(z, x, y, now):
    """Cool this tile and feed the breaker: TILE_BREAKER_FAILS failures within the window trip it."""
    _neg[(z, x, y)] = now + cfg.TILE_FAIL_COOLDOWN_S
    _fails.append(now)
    cutoff = now - cfg.TILE_BREAKER_WINDOW_S
    while _fails and _fails[0] < cutoff:
        _fails.pop(0)
    if len(_fails) >= cfg.TILE_BREAKER_FAILS:
        _breaker["until"] = now + cfg.TILE_BREAKER_COOLDOWN_S
        _fails[:] = []


def _note_success(now):
    """A good fetch (incl. the post-cooldown probe) clears the failure window + the breaker."""
    _fails[:] = []
    _breaker["until"] = 0.0


def _parse_retry_after(value):
    """Retry-After as integer seconds; an HTTP-date form just falls back to the cooldown (0)."""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


# --- tile cache + fetch (best-effort I/O; a disk hiccup degrades to a cache miss) --------

def _tile_cache_path(z, x, y):
    return os.path.join(cfg.TILE_CACHE_DIR, str(z), str(x), "%d.png" % y)


def _tile_url(z, x, y):
    return cfg.TILE_URL_TEMPLATE.format(z=z, x=x, y=y, key=cfg.TILE_API_KEY)


def _cache_write(path, data):
    """Best-effort write-back. A failed write (full disk / unmount / transient I/O) is
    swallowed — we just won't have the tile cached and will re-fetch it next time."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError:
        pass


def _cache_read(z, x, y):
    """Bytes from the disk cache only (no network). None on miss or a disk read error."""
    try:
        with open(_tile_cache_path(z, x, y), "rb") as f:
            return f.read()
    except OSError:
        return None


def _http_get(z, x, y, now):
    """Live HTTP fetch of one tile (PNG bytes or None). A 429/Retry-After trips the breaker."""
    try:
        req = urllib.request.Request(_tile_url(z, x, y),
                                     headers={"User-Agent": cfg.GEO_USER_AGENT})
        with urllib.request.urlopen(req, timeout=cfg.TILE_TIMEOUT_S) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            ra = e.headers.get("Retry-After") if e.headers else None
            note_throttle(now, _parse_retry_after(ra))
        return None
    except Exception:
        return None


def fetch_tile(z, x, y, _net=None, _now=None):
    """PNG bytes for tile (z,x,y): disk cache first; then — unless this tile is cooled or the
    global breaker is open — a live fetch, written back to the cache. Returns None on any
    miss+failure. Every disk op is wrapped so a disk I/O error degrades to a live fetch / a gap
    rather than crashing the render. `_net`/`_now` are injectable for tests (default: real HTTP
    + wall clock)."""
    data = _cache_read(z, x, y)
    if data is not None:
        return data
    now = time.time() if _now is None else _now
    # Don't re-hit a known-bad tile, or a provider we've tripped the breaker on.
    if _tile_cooled(z, x, y, now) or is_throttled(now):
        return None
    # No key for a key-templated provider -> offline; don't hammer with bad requests (and don't
    # count it as a provider failure). Skipped when a test injects its own network.
    if _net is None and "{key}" in cfg.TILE_URL_TEMPLATE and not cfg.TILE_API_KEY:
        return None
    try:
        data = _http_get(z, x, y, now) if _net is None else _net(z, x, y)
    except Exception:
        data = None
    if data is None:
        _note_tile_failure(z, x, y, now)
        return None
    _note_success(now)
    _cache_write(_tile_cache_path(z, x, y), data)
    return data


def _lowzoom_fill(z, x, y, max_steps=6):
    """Approximate a missing tile from a cached lower-zoom ancestor (the matching quadrant,
    upsampled) so a dead-zone gap shows blurry context instead of flat fill. Cache-only — it
    never fetches. Returns a 256px Image or None."""
    for dz in range(1, min(z, max_steps) + 1):
        data = _cache_read(z - dz, x >> dz, y >> dz)
        if data is None:
            continue
        try:
            im = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            continue
        f = 2 ** dz
        sub = TILE // f
        ox, oy = (x % f) * sub, (y % f) * sub
        return im.crop((ox, oy, ox + sub, oy + sub)).resize((TILE, TILE), Image.BILINEAR)
    return None


def basemap(center, z, w, h, fetch=None):
    """Stitch the viewport's tiles onto one (w,h) RGB canvas. A tile that can't be fetched is
    approximated from a cached lower-zoom ancestor when possible, else left as flat fill.

    Returns (Image, stats) with stats = {tiles, fetched, filled, missing}. `fetch` is injectable
    for testing; it defaults to fetch_tile.
    """
    if fetch is None:
        fetch = fetch_tile
    canvas = Image.new("RGB", (w, h), GAP_RGB)
    n = 2 ** z
    placed = tiles_for_viewport(center, z, w, h)
    # Fetch the in-range tiles CONCURRENTLY. The first render of a new area is I/O-bound on the
    # tile server (cold cache over LTE), so a thread pool turns ~40 sequential round-trips into
    # a few parallel batches — the difference between a snappy frame and a 40 s stall.
    want = {(x, y) for (x, y, _sx, _sy) in placed if 0 <= y < n}
    got = {}
    if want:
        with ThreadPoolExecutor(max_workers=min(cfg.TILE_FETCH_WORKERS, len(want))) as ex:
            futs = {ex.submit(fetch, z, x, y): (x, y) for (x, y) in want}
            for fut in futs:
                try:
                    got[futs[fut]] = fut.result()
                except Exception:
                    got[futs[fut]] = None
    fetched = filled = missing = 0
    for (x, y, sx, sy) in placed:
        img = None
        data = got.get((x, y)) if 0 <= y < n else None
        if data is not None:
            try:
                img = Image.open(io.BytesIO(data)).convert("RGB")
            except Exception:
                img = None
        if img is not None:
            fetched += 1
        else:
            img = _lowzoom_fill(z, x, y) if 0 <= y < n else None
            if img is None:
                missing += 1
                continue
            filled += 1
        canvas.paste(img, (int(round(sx)), int(round(sy))))
    return canvas, {"tiles": fetched + filled + missing, "fetched": fetched,
                    "filled": filled, "missing": missing,
                    "throttled": is_throttled(time.time())}
