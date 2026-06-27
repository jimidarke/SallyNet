"""waypoints.py — trip waypoint helpers shared by the API + map compositor.

Canonical store is /var/lib/sally/waypoints.json (phone-edited at /waypoints, re-read each
render). This module holds the pure selection logic — which waypoint is "next" — used by the
map status-strip countdown and the pin emphasis. Stdlib only (no Pillow) so it imports cheaply
and is unit-tested off the Pi.
"""
import math

VALID_TYPES = ("fuel", "camp", "scenic", "stop")


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def select_next_waypoint(waypoints, lat, lon):
    """Return (waypoint, straight_km) for the 'next' unvisited waypoint, or None.

    Route-ordered: among unvisited waypoints with an `order`, pick the lowest. If none of the
    unvisited waypoints carry an `order`, fall back to the nearest by great-circle distance
    (needs a GPS position; otherwise just the first). `straight_km` is None without a position.
    Records flagged `favourite` are saved places, not route stops — always excluded.
    """
    unvisited = [w for w in waypoints
                 if not w.get("visited")
                 and not w.get("favourite")  # favourites are saved places, never route stops
                 and w.get("lat") is not None and w.get("lon") is not None]
    if not unvisited:
        return None
    have_pos = lat is not None and lon is not None
    ordered = [w for w in unvisited if w.get("order") is not None]
    if ordered:
        nxt = min(ordered, key=lambda w: w["order"])
    elif have_pos:
        nxt = min(unvisited, key=lambda w: haversine_km(lat, lon, w["lat"], w["lon"]))
    else:
        nxt = unvisited[0]
    km = round(haversine_km(lat, lon, nxt["lat"], nxt["lon"]), 1) if have_pos else None
    return (nxt, km)
