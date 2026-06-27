"""mapgen.py — compose the ambient map PNG the Roku displays.

`render_map_png()` is the only entry point the /api/map.png route calls. It bakes, in draw
order: basemap (tiles.py) -> [trail -> POI -> waypoints -> labels: P2-P4] -> Sally's arrow
(centred, on top) -> status strip + attribution. The vector overlay is drawn at 2x and
LANCZOS-downscaled so lines/markers are anti-aliased (Pillow's draw ops are not).

An in-RAM single-flight cache stops the Pi re-rendering identical frames for every Roku poll
(see _reuse_cached). Written for the Pi's EOL-Buster Pillow: legacy resampling constants only,
no ImageDraw text `anchor=`, text measured version-robustly.
"""
import io
import math
import os
import threading
import time

from PIL import Image, ImageDraw, ImageFont

import sallyconf as cfg
import tiles
import waypoints  # haversine for the photo-POI distance cull (stdlib-only, no circular import)

SUPER = 2  # supersample factor for the anti-aliased vector overlay

# Channel palette (matches the guest pages' --r/--o/--g/--ink).
RED = (192, 57, 43)
GOLD = (212, 160, 23)
INK = (43, 43, 43)
WHITE = (255, 255, 255)
STRIP_RGB = (20, 22, 26)
STRIP_ALPHA = 190
GREEN = (39, 174, 96)
AMBER = (230, 126, 34)
TRAIL_RGBA = (51, 122, 183, 225)  # navigation blue, cased in white for contrast
WP_COLORS = {  # waypoint pin colours by type
    "fuel": (39, 174, 96), "camp": (230, 126, 34),
    "scenic": (142, 68, 173), "stop": (212, 160, 23),
}
POI_COLORS = {  # POI glyph colours by category (RV-essentials / fuel / scenic)
    "rv": (39, 174, 96), "fuel": (41, 128, 185), "scenic": (142, 68, 173),
}
POI_CAP = {10: 6, 11: 8, 12: 10, 13: 16, 14: 22, 15: 28}  # max glyphs shown, by zoom
PHOTO_RGB = (214, 51, 132)  # past-trip photo glyph (magenta) — distinct from POI dots / waypoint pins

ALL_LAYERS = ("base", "trail", "poi", "photos", "waypoints", "labels", "status")

_fonts = {}


def _font(size, bold=False):
    key = (size, bold)
    if key not in _fonts:
        path = cfg.MAP_FONT_PATH
        if bold:
            bp = os.path.join(os.path.dirname(path), "DejaVuSans-Bold.ttf")
            if os.path.exists(bp):
                path = bp
        try:
            _fonts[key] = ImageFont.truetype(path, size)
        except Exception:
            _fonts[key] = ImageFont.load_default()
    return _fonts[key]


def _text_w(draw, s, font):
    """Text width in px, robust across Pillow versions (textlength >=8, getsize on Buster)."""
    try:
        return int(draw.textlength(s, font=font))
    except AttributeError:
        return font.getsize(s)[0]


# --- Sally's marker -----------------------------------------------------------------------

def _rot(cx, cy, heading_deg, rel_deg, dist):
    """Point at `dist` from (cx,cy) along (heading+rel), screen coords (y down, 0deg = up)."""
    a = math.radians(heading_deg + rel_deg)
    return (cx + dist * math.sin(a), cy - dist * math.cos(a))


def _expand(pts, cx, cy, k):
    return [(cx + (x - cx) * k, cy + (y - cy) * k) for (x, y) in pts]


def _draw_trail(od, points, center, zoom, w, h, scale):
    """Today's breadcrumb as a white-cased blue polyline behind Sally (drawn on the 2x
    overlay so it's anti-aliased). Points are (lat, lon) in chronological order."""
    if not points or len(points) < 2:
        return
    pts = []
    for p in points:
        x, y = tiles.project(p[0], p[1], center, zoom, w, h)
        pts.append((x * scale, y * scale))
    od.line(pts, fill=(255, 255, 255, 140), width=max(1, int(9 * scale)), joint="curve")
    od.line(pts, fill=TRAIL_RGBA, width=max(1, int(5 * scale)), joint="curve")


def _label(od, x, y, text, font, color):
    """A small dark pill + text on the overlay (legible over any basemap)."""
    if not text:
        return
    tw = _text_w(od, text, font)
    asc, desc = font.getmetrics()
    th = asc + desc
    od.rectangle([x - 6, y - 4, x + tw + 6, y + th + 4], fill=(20, 22, 26, 170))
    od.text((x, y), text, font=font, fill=color)


def _pin(od, px, py, color, r, emphasize):
    """A teardrop pin whose tip is at (px, py) = the projected ground coord."""
    hx, hy = px, py - r * 1.7
    if emphasize:  # gold ring (drawn under the white casing so a rim shows)
        od.ellipse([hx - r - 7, hy - r - 7, hx + r + 7, hy + r + 7], fill=GOLD + (255,))
    od.ellipse([hx - r - 2, hy - r - 2, hx + r + 2, hy + r + 2], fill=WHITE + (235,))
    od.polygon([(px, py), (hx - r * 0.78, hy + r * 0.35), (hx + r * 0.78, hy + r * 0.35)],
               fill=WHITE + (235,))
    od.ellipse([hx - r, hy - r, hx + r, hy + r], fill=color + (255,))
    od.polygon([(px, py), (hx - r * 0.6, hy + r * 0.2), (hx + r * 0.6, hy + r * 0.2)],
               fill=color + (255,))
    od.ellipse([hx - r * 0.38, hy - r * 0.38, hx + r * 0.38, hy + r * 0.38], fill=WHITE + (240,))


def _star(od, cx, cy, r, color):
    """A 5-point star centred at (cx, cy), white-cased then filled — the favourite marker,
    shape-distinct from the teardrop pins and the 'next' gold ring."""
    pts = []
    for i in range(10):
        rad = r if i % 2 == 0 else r * 0.42
        a = math.radians(-90 + i * 36)
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    od.polygon(_expand(pts, cx, cy, 1.25), fill=WHITE + (255,))
    od.polygon(pts, fill=color + (255,))


def _draw_poi(od, poi, center, zoom, w, h, scale, show_labels):
    """RV-essential / fuel / scenic POI as small cased dots. Decluttered by zoom (cap by
    POI_CAP, nearest-to-centre kept), with name labels only on the closest few."""
    regions = (poi or {}).get("regions") or []
    seen = set()
    cx, cy = w / 2.0, h / 2.0
    placed = []
    for rg in regions:
        for cat, items in (rg.get("categories") or {}).items():
            color = POI_COLORS.get(cat)
            if not color:
                continue
            for it in (items or []):
                lat, lon = it.get("lat"), it.get("lon")
                if lat is None or lon is None:
                    continue
                k = (round(lat, 5), round(lon, 5))
                if k in seen:
                    continue
                seen.add(k)
                x, y = tiles.project(lat, lon, center, zoom, w, h)
                if not (-40 < x < w + 40 and -40 < y < h + 40):
                    continue
                placed.append(((x - cx) ** 2 + (y - cy) ** 2, color, it, x, y))
    if not placed:
        return
    placed.sort(key=lambda t: t[0])
    placed = placed[:POI_CAP.get(zoom, 12)]
    font = _font(int(16 * scale), bold=True)
    for i, (_d2, color, it, x, y) in enumerate(placed):
        px, py, r = x * scale, y * scale, 8 * scale
        od.ellipse([px - r - 2, py - r - 2, px + r + 2, py + r + 2], fill=WHITE + (230,))
        od.ellipse([px - r, py - r, px + r, py + r], fill=color + (255,))
        od.ellipse([px - r * 0.34, py - r * 0.34, px + r * 0.34, py + r * 0.34], fill=WHITE + (235,))
        if show_labels and i < 4 and it.get("name"):
            _label(od, px + r + 5 * scale, py - r, it["name"], font, WHITE + (230,))


def _draw_photo_poi(od, photo, center, zoom, w, h, scale, show_labels, max_km):
    """Past-trip photo pins (cased magenta camera squares). Same declutter as _draw_poi (off-canvas
    cull, POI_CAP by zoom, nearest-to-centre kept, label the closest few) PLUS a hard great-circle
    cull so a far-away trip's photo never draws even when it projects on-canvas at low zoom."""
    items = (photo or {}).get("photos") or []
    if not items:
        return
    cx, cy = w / 2.0, h / 2.0
    placed, seen = [], set()
    for it in items:
        lat, lon = it.get("lat"), it.get("lon")
        if lat is None or lon is None:
            continue
        if waypoints.haversine_km(center[0], center[1], lat, lon) > max_km:
            continue  # a far trip's photo — never bleed it onto the current view
        k = (round(lat, 5), round(lon, 5))
        if k in seen:
            continue
        seen.add(k)
        x, y = tiles.project(lat, lon, center, zoom, w, h)
        if not (-40 < x < w + 40 and -40 < y < h + 40):
            continue
        placed.append(((x - cx) ** 2 + (y - cy) ** 2, it, x, y))
    if not placed:
        return
    placed.sort(key=lambda t: t[0])
    placed = placed[:POI_CAP.get(zoom, 12)]
    font = _font(int(16 * scale), bold=True)
    for i, (_d2, it, x, y) in enumerate(placed):
        px, py, r = x * scale, y * scale, 9 * scale
        od.rectangle([px - r - 2, py - r - 2, px + r + 2, py + r + 2], fill=WHITE + (235,))
        od.rectangle([px - r, py - r, px + r, py + r], fill=PHOTO_RGB + (255,))
        od.ellipse([px - r * 0.45, py - r * 0.45, px + r * 0.45, py + r * 0.45], fill=WHITE + (240,))
        if show_labels and i < 4 and it.get("title"):
            _label(od, px + r + 5 * scale, py - r, it["title"], font, WHITE + (230,))


def _draw_waypoints(od, wdata, nxt, center, zoom, w, h, scale, show_labels):
    """Trip waypoint pins (coloured by type), the 'next' one emphasised + counted down."""
    wlist = (wdata or {}).get("waypoints") or []
    if not wlist:
        return
    nxt_id = nxt.get("id") if nxt else None
    nxt_km = nxt.get("km") if nxt else None
    font = _font(int(19 * scale), bold=True)
    for wp in wlist:
        if wp.get("lat") is None or wp.get("lon") is None:
            continue
        x, y = tiles.project(wp["lat"], wp["lon"], center, zoom, w, h)
        px, py = x * scale, y * scale
        if not (-80 * scale < px < (w + 80) * scale and -100 * scale < py < (h + 40) * scale):
            continue  # well off-canvas
        is_next = (wp.get("id") == nxt_id)
        if wp.get("favourite"):  # a saved place — gold star, never the emphasised "next"
            r = 13 * scale
            _star(od, px, py, r, GOLD)
        else:
            color = WP_COLORS.get(wp.get("type"), WP_COLORS["stop"])
            r = (16 if is_next else 11) * scale
            _pin(od, px, py, color, r, is_next)
        if show_labels:
            label = wp.get("name") or ""
            if is_next and nxt_km is not None:
                label = label + "   " + ("%.1f km" % nxt_km)
            if wp.get("favourite") or is_next:
                lcolor = GOLD + (255,)
            elif wp.get("visited"):
                lcolor = (200, 200, 200, 160)
            else:
                lcolor = WHITE + (235,)
            _label(od, px + r + 6 * scale, py - r * 2.4, label, font, lcolor)


def _draw_marker(od, cx, cy, telemetry, scale):
    """Sally: a heading arrow when moving with a fix, else a neutral dot. White halo so it
    reads on any basemap. Drawn on the 2x overlay so it's anti-aliased."""
    r = 28.0 * scale
    heading = telemetry.get("heading")
    if telemetry.get("fix") and heading is not None:
        pts = [_rot(cx, cy, heading, 0, r),          # tip (forward)
               _rot(cx, cy, heading, 138, r * 0.95),  # right wing
               _rot(cx, cy, heading, 180, r * 0.34),  # concave tail notch
               _rot(cx, cy, heading, -138, r * 0.95)]  # left wing
        od.polygon(_expand(pts, cx, cy, 1.22), fill=WHITE + (235,))
        od.polygon(pts, fill=RED + (255,))
    else:
        od.ellipse([cx - r * 0.82, cy - r * 0.82, cx + r * 0.82, cy + r * 0.82], fill=WHITE + (235,))
        od.ellipse([cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55], fill=RED + (255,))


# --- status strip -------------------------------------------------------------------------

def _chip(draw, x, y, label, value, color, font, font_b):
    """Right-to-left chip: returns the new right edge x to the left of what was drawn."""
    vw = _text_w(draw, value, font_b)
    lw = _text_w(draw, label, font)
    draw.text((x - vw, y), value, font=font_b, fill=color)
    draw.text((x - vw - 8 - lw, y), label, font=font, fill=(200, 200, 200))
    return x - vw - 8 - lw - 22


def _map_chip_state(base_stats):
    """Bottom-strip MAP chip (value, colour): throttled > gaps > approx > ok. A tripped tile
    breaker shows 'throttled' so a stale basemap from a backed-off provider is obvious."""
    if base_stats.get("throttled"):
        return ("throttled", AMBER)
    if base_stats.get("missing", 0) > 0:
        return ("%d gaps" % base_stats["missing"], AMBER)
    if base_stats.get("filled", 0) > 0:
        return ("approx", AMBER)
    return ("ok", GREEN)


def _draw_status(canvas, center, zoom, telemetry, data, base_stats):
    w, h = canvas.size
    sh = 64
    # Translucent bar via a uniform alpha mask (no full-canvas convert — cheap on the Pi).
    canvas.paste(Image.new("RGB", (w, sh), STRIP_RGB), (0, h - sh),
                 Image.new("L", (w, sh), STRIP_ALPHA))
    d = ImageDraw.Draw(canvas)
    f = _font(24)
    fb = _font(30, bold=True)
    fsm = _font(15)
    top = h - sh + 10

    # Left: speed (hero) + altitude.
    spd = telemetry.get("speed_kmh") or 0.0
    d.text((24, h - sh + 6), "%.0f" % spd, font=fb, fill=WHITE)
    sw = _text_w(d, "%.0f" % spd, fb)
    d.text((24 + sw + 6, top + 4), "km/h", font=fsm, fill=(200, 200, 200))
    alt = telemetry.get("alt_m")
    nxt_x = 24 + sw + 70
    if alt is not None:
        alt_txt = "alt %d m" % int(round(alt))
        d.text((nxt_x, top), alt_txt, font=f, fill=(225, 225, 225))
        nxt_x += _text_w(d, alt_txt, f) + 28

    # Centre: next waypoint (P3 fills route.json-style data; P1 shows a placeholder).
    nxt = (data or {}).get("nextWaypoint")
    if nxt and nxt.get("name"):
        km = nxt.get("km")
        txt = "→ %s" % nxt["name"]
        if km is not None:
            txt += "   %.1f km" % km
        d.text((nxt_x, top), txt, font=f, fill=GOLD)

    # Right: GPS fix + basemap-completeness chips.
    edge = w - 24
    map_val, map_col = _map_chip_state(base_stats)
    edge = _chip(d, edge, top, "MAP", map_val, map_col, f, fb)
    if telemetry.get("fix"):
        mode = telemetry.get("mode")
        fixv = ("%dD " % mode if mode in (2, 3) else "") + "%d sats" % (telemetry.get("sats") or 0)
        _chip(d, edge, top, "GPS", fixv.strip(), GREEN, f, fb)
    else:
        _chip(d, edge, top, "GPS", "no fix", AMBER, f, fb)

    # Attribution (license requirement) — small, bottom-left inside the strip.
    d.text((24, h - 20), cfg.TILE_ATTRIBUTION, font=fsm, fill=(150, 150, 150))


def _fmt_age(s):
    s = int(s or 0)
    return "%dm %02ds" % (s // 60, s % 60) if s >= 60 else "%ds" % s


def _draw_gps_alert(canvas, telemetry):
    """Always-on GPS-loss safety overlay. Deliberately NOT a member of ALL_LAYERS, so a viewer
    can't toggle it off and it never enters the cache shape key. A top banner (clear of the bottom
    status strip); the map underneath stays FROZEN at the last-known position. RED once a prior fix
    is lost; AMBER while still acquiring the first fix."""
    if telemetry.get("fix"):
        return
    age = telemetry.get("fix_age_s")
    if age is None or age < cfg.MAP_GPS_ALERT_AFTER_S:
        return
    w, _h = canvas.size
    bh = 70
    if telemetry.get("had_fix"):
        bg, head, sub = RED, "GPS SIGNAL LOST", "no fix for %s — showing last position" % _fmt_age(age)
    else:
        bg, head, sub = AMBER, "WAITING FOR GPS", "acquiring fix… %s" % _fmt_age(age)
    canvas.paste(Image.new("RGB", (w, bh), bg), (0, 0), Image.new("L", (w, bh), 210))
    d = ImageDraw.Draw(canvas)
    d.text((24, 8), head, font=_font(34, bold=True), fill=WHITE)
    d.text((24, 46), sub, font=_font(18), fill=(245, 235, 230))


# --- compose + cache ----------------------------------------------------------------------

def _layer_on(layers, name):
    return layers is None or name in layers


def _compose(center, zoom, w, h, layers, telemetry, data):
    if _layer_on(layers, "base"):
        canvas, base_stats = tiles.basemap(center, zoom, w, h)
    else:
        canvas, base_stats = Image.new("RGB", (w, h), tiles.GAP_RGB), {"missing": 0, "fetched": 0}

    # Anti-aliased vector overlay (trail/POI/waypoints land here in P2-P4; arrow always).
    ov = Image.new("RGBA", (w * SUPER, h * SUPER), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    if _layer_on(layers, "trail"):
        _draw_trail(od, (data or {}).get("trail") or [], center, zoom, w, h, SUPER)
    if _layer_on(layers, "poi"):
        _draw_poi(od, (data or {}).get("poi"), center, zoom, w, h, SUPER, _layer_on(layers, "labels"))
    if _layer_on(layers, "photos"):
        _draw_photo_poi(od, (data or {}).get("photoPoi"), center, zoom, w, h, SUPER,
                        _layer_on(layers, "labels"), cfg.PHOTO_POI_MAX_KM)
    if _layer_on(layers, "waypoints"):
        _draw_waypoints(od, (data or {}).get("waypoints"), (data or {}).get("nextWaypoint"),
                        center, zoom, w, h, SUPER, _layer_on(layers, "labels"))
    _draw_marker(od, w * SUPER // 2, h * SUPER // 2, telemetry, SUPER)
    ov = ov.resize((w, h), Image.LANCZOS)
    canvas.paste(ov, (0, 0), ov)

    if _layer_on(layers, "status"):
        _draw_status(canvas, center, zoom, telemetry, data, base_stats)

    _draw_gps_alert(canvas, telemetry)  # always-on safety overlay, on top of everything

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", compress_level=1)  # LAN delivery: speed over size on ARM
    return buf.getvalue()


def _reuse_cached(now, last_at, last_shape, shape, last_content, content,
                  min_interval, parked_ttl):
    """Decide whether to serve the cached PNG instead of re-composing.

    - Nothing cached yet -> render.
    - Different shape (canvas size / layer set) -> render; a differently-shaped frame can't
      be reused even within the throttle window.
    - Same shape + same content (parked: centre rounds identically) within PARKED_TTL -> reuse.
    - Same shape, otherwise within MIN_RENDER_INTERVAL of the last render -> reuse (throttle).
    - Else render.
    """
    if last_shape is None:
        return False
    if shape != last_shape:
        return False
    if content == last_content and (now - last_at) < parked_ttl:
        return True
    if (now - last_at) < min_interval:
        return True
    return False


def _data_sig(data):
    """Cheap signature of the dynamic layers so an edit (new breadcrumb, moved waypoint,
    fresh ETA) busts the cache, but live speed/heading/clock do not."""
    data = data or {}
    trail = data.get("trail") or []
    wpts = (data.get("waypoints") or {}).get("waypoints") or []
    poi = data.get("poi") or {}
    photo = data.get("photoPoi") or {}
    route = data.get("route") or {}
    nxt = data.get("nextWaypoint") or {}
    return (
        len(trail), tuple(trail[-1]) if trail else None,
        len(wpts), max((wp.get("updatedTs", 0) for wp in wpts), default=0),
        sum(len(r.get("categories", {}).get(k, [])) for r in poi.get("regions", []) for k in ("rv", "fuel", "scenic")),
        len(photo.get("photos") or []), photo.get("generated"),
        route.get("computed_at"), nxt.get("id"), nxt.get("km") is not None,
    )


def _content_sig(center, zoom, data):
    # Round centre so GPS jitter while parked keeps the signature stable (~110 m at 3 dp).
    rc = (round(center[0], 3), round(center[1], 3))
    return (rc, zoom, _data_sig(data))


def _alert_sig(telemetry):
    """A coarse 5 s bucket of the GPS-loss age, folded into the content sig so the banner + its
    counter refresh promptly (~every 5 s) instead of being up to PARKED_TTL stale. None when no
    banner is active (so normal frames keep their exact cache behaviour)."""
    if telemetry.get("fix"):
        return None
    age = telemetry.get("fix_age_s")
    if age is None or age < cfg.MAP_GPS_ALERT_AFTER_S:
        return None
    return int(age // 5)


def _shape_sig(w, h, layers):
    return (w, h, tuple(sorted(layers)) if layers else "all")


_lock = threading.Lock()
_last = {"png": None, "at": 0.0, "shape": None, "content": None}


def reset_render_cache():
    """Drop the in-RAM single-flight frame cache (tests, or a forced refresh)."""
    _last.update(png=None, at=0.0, shape=None, content=None)


def render_map_png(center, zoom, w, h, layers, telemetry, data, now=None):
    """Compose (or reuse a cached) PNG. `now` is injectable for tests."""
    if now is None:
        now = time.time()
    shape = _shape_sig(w, h, layers)
    content = _content_sig(center, zoom, data)
    asig = _alert_sig(telemetry)
    if asig is not None:
        content = content + ("gps", asig)  # the active GPS-loss banner must bust the frame cache

    def reuse(t):
        return _last["png"] is not None and _reuse_cached(
            t, _last["at"], _last["shape"], shape, _last["content"], content,
            cfg.MAP_MIN_RENDER_INTERVAL_S, cfg.MAP_PARKED_TTL_S)

    if reuse(now):
        return _last["png"]
    with _lock:
        # Re-check under the lock so concurrent polls coalesce onto one render.
        if reuse(now):
            return _last["png"]
        png = _compose(center, zoom, w, h, layers, telemetry, data)
        _last.update(png=png, at=now, shape=shape, content=content)
        return png
