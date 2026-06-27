#!/usr/bin/env python3
"""trip-eta-refresh.py — refresh the OSRM road-route ETA cache for the active trip.

Runs off a 60 s systemd timer. It is a thin LOCALHOST client of sally-api: it reads
/api/state (so it never re-implements gpsd or the trip store), and when there's an
active trip with a destination pin and a current GPS fix, it asks OSRM for the road
distance + duration and writes the result to ROUTE_JSON. /api/state then folds that
cache into its `trip` section as the ETA — keeping the 5 s Roku poll fast and
network-free, and letting the ETA go gracefully stale in cellular dead zones (this
script simply leaves the last good cache in place when the network is down).

No-ops (writes nothing) unless: active trip + dest coords + GPS fix + not-yet-arrived
+ OSRM reachable. Dependency-free stdlib so it runs on the Pi's EOL Buster.

Env (all overridable; N100 migration is an endpoint/path change):
  SALLY_API_LOCAL  sally-api base       (default http://127.0.0.1:8090)
  ROUTE_JSON       ETA cache out        (default /var/lib/sally/route.json)
  OSRM_URL         OSRM driving profile (default public demo server)
  DEST_RADIUS_M    "arrived" threshold  (default 250) — skip when already at camp
"""
import fcntl
import json
import os
import sys
import time
import urllib.request

API_LOCAL = os.environ.get("SALLY_API_LOCAL", "http://127.0.0.1:8090").rstrip("/")
ROUTE_JSON = os.environ.get("ROUTE_JSON", "/var/lib/sally/route.json")
OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org/route/v1/driving")
DEST_RADIUS_M = float(os.environ.get("SALLY_DEST_RADIUS_M", "250"))


def _get_json(url, timeout):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


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
    except Exception as e:
        print("no state (%s) — skip" % e)
        return 0

    trip = state.get("trip")
    gps = state.get("gps") or {}
    if not trip or not trip.get("dest") or not gps.get("fix"):
        print("no active trip with dest + fix — skip")
        return 0

    km_to_dest = trip.get("km_to_dest")
    if km_to_dest is not None and km_to_dest * 1000.0 <= DEST_RADIUS_M:
        print("already at destination — skip")
        return 0

    src = (gps["lon"], gps["lat"])
    dst = (trip["dest"]["lon"], trip["dest"]["lat"])
    coords = "%f,%f;%f,%f" % (src[0], src[1], dst[0], dst[1])
    url = OSRM_URL + "/" + coords + "?overview=false&alternatives=false"
    try:
        route = _get_json(url, timeout=10)
    except Exception as e:
        print("OSRM unreachable (%s) — keeping last cache" % e)
        return 0
    if route.get("code") != "Ok" or not route.get("routes"):
        print("OSRM no route (%s) — keeping last cache" % route.get("code"))
        return 0

    r0 = route["routes"][0]
    now = int(time.time())
    cache = {
        "tripId": trip.get("id"),
        "road_km": round(r0["distance"] / 1000.0, 1),
        "eta_epoch": now + int(r0["duration"]),
        "computed_at": now,
    }
    _atomic_write_json(ROUTE_JSON, cache)
    print("ETA cached: %s in %d min (%.1f km) -> %s"
          % (cache["tripId"], int(r0["duration"]) // 60, cache["road_km"], ROUTE_JSON))
    return 0


if __name__ == "__main__":
    sys.exit(main())
