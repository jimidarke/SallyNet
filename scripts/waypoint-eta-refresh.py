#!/usr/bin/env python3
"""waypoint-eta-refresh.py — road-km/ETA to the next trip waypoint + arrival auto-advance.

Runs off a 60 s systemd timer. A thin LOCALHOST client of sally-api: reads /api/state (gps) and
/api/waypoints, picks the next unvisited waypoint (route order), marks it visited via the API
when Sally arrives (within its arriveRadiusM), and caches the OSRM road distance + ETA to the
next one in WAYPOINT_ROUTE_JSON. /api/map.png folds that cache into the status-strip countdown,
preferring it over straight-line km and falling back to straight-line in cellular dead zones.

No-ops cheaply unless: a GPS fix + at least one unvisited waypoint + OSRM reachable. The
canonical next-waypoint logic is reused from the deployed sally-api (SALLY_API_DIR) so it never
diverges; if that import fails the script simply skips (the map keeps using straight-line km).
Dependency-free stdlib so it runs on the Pi's EOL Buster.

Env (all overridable):
  SALLY_API_LOCAL      sally-api base        (default http://127.0.0.1:8090)
  SALLY_API_DIR        deployed app dir      (default /opt/sally/sally-api) — for the import
  WAYPOINT_ROUTE_JSON  ETA cache out         (default /var/lib/sally/waypoint-route.json)
  OSRM_URL             OSRM driving profile  (default public demo server)
"""
import fcntl
import json
import os
import sys
import time
import urllib.parse
import urllib.request

API_LOCAL = os.environ.get("SALLY_API_LOCAL", "http://127.0.0.1:8090").rstrip("/")
WAYPOINT_ROUTE_JSON = os.environ.get("WAYPOINT_ROUTE_JSON", "/var/lib/sally/waypoint-route.json")
OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org/route/v1/driving")

sys.path.insert(0, os.environ.get("SALLY_API_DIR", "/opt/sally/sally-api"))
try:
    from waypoints import select_next_waypoint
except Exception as e:  # noqa: BLE001 — degrade, don't crash the timer
    print("cannot import sally-api waypoints module (%s) — skip" % e)
    sys.exit(0)


def _get_json(url, timeout=8, data=None):
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post_form(url, fields, timeout=5):
    data = urllib.parse.urlencode(fields).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=timeout) as r:
        return r.read()


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


def main():
    try:
        state = _get_json(API_LOCAL + "/api/state", timeout=5)
        wps = _get_json(API_LOCAL + "/api/waypoints", timeout=5).get("waypoints") or []
    except Exception as e:  # noqa: BLE001
        print("no state/waypoints (%s) — skip" % e)
        return 0

    gps = state.get("gps") or {}
    if not gps.get("fix") or gps.get("lat") is None:
        print("no fix — skip")
        return 0
    lat, lon = gps["lat"], gps["lon"]

    # Arrival auto-advance: while the next waypoint is within its radius, mark it visited (via
    # the API, which owns waypoints.json) and re-pick. Bounded by the waypoint count.
    for _ in range(len(wps) + 1):
        sel = select_next_waypoint(wps, lat, lon)
        if not sel:
            break
        w, km = sel
        radius_km = (w.get("arriveRadiusM") or 250.0) / 1000.0
        if km is None or km > radius_km:
            break
        try:
            _post_form(API_LOCAL + "/api/waypoints", {"op": "visit", "id": w["id"], "visited": "1"})
            print("arrived %s — marked visited" % w.get("name"))
            for x in wps:
                if x.get("id") == w.get("id"):
                    x["visited"] = True
        except Exception as e:  # noqa: BLE001
            print("visit POST failed (%s) — skip advance" % e)
            break

    sel = select_next_waypoint(wps, lat, lon)
    if not sel:
        print("no next waypoint — skip")
        return 0
    w, _km = sel
    coords = "%f,%f;%f,%f" % (lon, lat, w["lon"], w["lat"])
    try:
        route = _get_json(OSRM_URL + "/" + coords + "?overview=false&alternatives=false", timeout=10)
    except Exception as e:  # noqa: BLE001
        print("OSRM unreachable (%s) — keeping last cache" % e)
        return 0
    if route.get("code") != "Ok" or not route.get("routes"):
        print("OSRM no route (%s) — keeping last cache" % route.get("code"))
        return 0

    r0 = route["routes"][0]
    now = int(time.time())
    _atomic_write_json(WAYPOINT_ROUTE_JSON, {
        "wpId": w["id"],
        "road_km": round(r0["distance"] / 1000.0, 1),
        "eta_epoch": now + int(r0["duration"]),
        "computed_at": now,
    })
    print("waypoint ETA cached: %s in %d min (%.1f km)"
          % (w.get("name"), int(r0["duration"]) // 60, r0["distance"] / 1000.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
