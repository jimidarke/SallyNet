#!/usr/bin/env python3
"""poi-refresh.py — snapshot nearby POI (RV-essentials / fuel / scenic) from Overpass.

Runs off a timer. Reads /api/state for Sally's position, and when she's moved far enough since
the last snapshot (or it's gone stale), queries Overpass for a bbox around her, trims each hit to
{name, lat, lon}, buckets it into rv/fuel/scenic, and writes POI_CACHE_JSON. /api/map.png draws
the glyphs from this cache and keeps serving the last snapshot (no refetch) in dead zones.

Polite to the public Overpass endpoint: one bbox query, only when Sally has moved > POI_MOVE_KM
or the snapshot is older than POI_MAX_AGE_S. Dependency-free stdlib (Buster).

Env: SALLY_API_LOCAL, POI_CACHE_JSON, OVERPASS_URL, POI_BBOX_DEG, POI_MOVE_KM, POI_MAX_AGE_S
"""
import fcntl
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

API_LOCAL = os.environ.get("SALLY_API_LOCAL", "http://127.0.0.1:8090").rstrip("/")
POI_CACHE_JSON = os.environ.get("POI_CACHE_JSON", "/var/lib/sally/poi-cache.json")
OVERPASS_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
BBOX_DEG = float(os.environ.get("POI_BBOX_DEG", "0.5"))      # +/- degrees around current pos
MOVE_KM = float(os.environ.get("POI_MOVE_KM", "10"))
MAX_AGE_S = int(os.environ.get("POI_MAX_AGE_S", "2700"))     # 45 min
PER_CAT_CAP = 80
# A descriptive UA is required by the OSM/Overpass usage policy — the default urllib UA is 406'd.
USER_AGENT = os.environ.get("GEO_USER_AGENT", "sally-api/1.0 (sallynet motorhome dashboard)")

QUERY = """[out:json][timeout:25];
(
  node[amenity=fuel](%(bbox)s);
  node[tourism=caravan_site](%(bbox)s);
  way[tourism=caravan_site](%(bbox)s);
  node[tourism=camp_site](%(bbox)s);
  node[amenity=sanitary_dump_station](%(bbox)s);
  node[tourism=viewpoint](%(bbox)s);
  node[natural=peak](%(bbox)s);
);
out center %(cap)d;
"""


def _haversine_km(a, b, c, d):
    r = 6371.0088
    p1, p2 = math.radians(a), math.radians(c)
    dp, dl = math.radians(c - a), math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def _read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _atomic_write_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lock = path + ".lock"
    with open(lock, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
        fcntl.flock(lf, fcntl.LOCK_UN)


def _get_json(url, timeout=8):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _categorize(tags):
    if tags.get("amenity") == "fuel":
        return "fuel"
    if (tags.get("tourism") in ("caravan_site", "camp_site")
            or tags.get("amenity") == "sanitary_dump_station"):
        return "rv"
    if tags.get("tourism") == "viewpoint" or tags.get("natural") == "peak":
        return "scenic"
    return None


def main():
    try:
        state = _get_json(API_LOCAL + "/api/state", timeout=5)
    except Exception as e:  # noqa: BLE001
        print("no state (%s) — skip" % e)
        return 0
    gps = state.get("gps") or {}
    if not gps.get("fix") or gps.get("lat") is None:
        print("no fix — skip")
        return 0
    lat, lon = gps["lat"], gps["lon"]

    # Rate-limit: skip if a recent snapshot already covers here.
    regions = (_read_json(POI_CACHE_JSON) or {}).get("regions") or []
    if regions:
        last = regions[0]
        c = last.get("center") or {}
        age = int(time.time()) - int(last.get("fetchedAt", 0))
        if (c.get("lat") is not None and age < MAX_AGE_S
                and _haversine_km(lat, lon, c["lat"], c["lon"]) < MOVE_KM):
            print("recent snapshot covers here (%ds old) — skip" % age)
            return 0

    bbox = "%f,%f,%f,%f" % (lat - BBOX_DEG, lon - BBOX_DEG, lat + BBOX_DEG, lon + BBOX_DEG)
    query = QUERY % {"bbox": bbox, "cap": 300}
    try:
        req = urllib.request.Request(
            OVERPASS_URL, data=("data=" + urllib.parse.quote(query)).encode(),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            res = json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001
        print("Overpass unreachable (%s) — keeping last snapshot" % e)
        return 0

    cats = {"rv": [], "fuel": [], "scenic": []}
    for el in res.get("elements", []):
        cat = _categorize(el.get("tags") or {})
        if not cat or len(cats[cat]) >= PER_CAT_CAP:
            continue
        center = el.get("center") or {}
        plat = el.get("lat", center.get("lat"))
        plon = el.get("lon", center.get("lon"))
        if plat is None or plon is None:
            continue
        cats[cat].append({"name": (el.get("tags") or {}).get("name") or cat.title(),
                          "lat": round(plat, 6), "lon": round(plon, 6)})

    snap = {"schemaVersion": 1, "regions": [{
        "bbox": [lat - BBOX_DEG, lon - BBOX_DEG, lat + BBOX_DEG, lon + BBOX_DEG],
        "center": {"lat": round(lat, 5), "lon": round(lon, 5)},
        "fetchedAt": int(time.time()),
        "categories": cats,
    }]}
    _atomic_write_json(POI_CACHE_JSON, snap)
    print("POI snapshot: rv=%d fuel=%d scenic=%d -> %s"
          % (len(cats["rv"]), len(cats["fuel"]), len(cats["scenic"]), POI_CACHE_JSON))
    return 0


if __name__ == "__main__":
    sys.exit(main())
