#!/usr/bin/env python3
"""nav-tick.py — the always-on GPS liveness heartbeat.

A Type=simple daemon (NOT a timer): one long-lived process that reads gpsd directly every
NAV_TICK_INTERVAL_S seconds, maintains the last-good-fix timestamp + a FROZEN last-known position,
and atomic-writes nav-state.json. That read-model is the source of truth the /api/map.png GPS-loss
overlay (and /api/state) use for fix-age, so signal loss is detected + counted even when nobody is
polling the map.

Why a daemon, not a timer: a ~7 s systemd timer would cold-start the interpreter ~12k times/day on
the Pi 3B+; one sleep-loop process is far cheaper. Why gpsd-direct (not /api/state): liveness must
not depend on sally-api being up, and there's no dependency loop. An SD-sparing write-gate
(navstate.should_write) keeps writes near-zero while parked-with-fix.

The pure decision logic lives in the importable sally-api `navstate` module (unit-tested off the
Pi in test_navstate.py); this script is just the gpsd read + loop + atomic write. Stdlib-only so it
runs on the Pi's EOL Buster.

Env (all overridable):
  SALLY_API_DIR        deployed app dir        (default /opt/sally/sally-api) — for the import
  NAV_STATE_JSON       nav-state out           (default /var/lib/sally/nav-state.json)
  NAV_TICK_INTERVAL_S  loop cadence seconds    (default 7)
  NAV_HEALTHY_WRITE_S  max gap between writes while fixed (default 30)
  NAV_MOVE_WRITE_M     write sooner if moved this far, m  (default 50)
  NAV_PREWARM          1 = warm tiles around current pos  (default 0; LICENSE-gated — only set
                       when the tile source PERMITS proactive fetching)
  GPSD_HOST/GPSD_PORT  gpsd endpoint           (default 127.0.0.1 / 2947)
  MAP_W/MAP_H          pre-warm canvas size    (default 1920/1080)
"""
import fcntl
import json
import os
import sys
import time

NAV_STATE_JSON = os.environ.get("NAV_STATE_JSON", "/var/lib/sally/nav-state.json")
NAV_TICK_INTERVAL_S = float(os.environ.get("NAV_TICK_INTERVAL_S", "7"))
NAV_HEALTHY_WRITE_S = float(os.environ.get("NAV_HEALTHY_WRITE_S", "30"))
NAV_MOVE_WRITE_M = float(os.environ.get("NAV_MOVE_WRITE_M", "50"))
NAV_PREWARM = os.environ.get("NAV_PREWARM", "0") not in ("", "0", "false", "False", "no")
GPSD_HOST = os.environ.get("GPSD_HOST", "127.0.0.1")
GPSD_PORT = int(os.environ.get("GPSD_PORT", "2947"))

sys.path.insert(0, os.environ.get("SALLY_API_DIR", "/opt/sally/sally-api"))
try:
    import navstate
    from gpsd_client import read_fix
except Exception as e:  # noqa: BLE001 — degrade, don't crash-loop the service
    print("cannot import sally-api navstate/gpsd_client (%s) — exiting" % e)
    sys.exit(0)


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


def _read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (ValueError, OSError):
        return default


def _prewarm(last_known):
    """Warm the on-disk tile cache around the current position so the next /api/map.png is
    instant. LICENSE NOTE: proactive pre-fetch is only compliant when the tile source permits it
    — hence NAV_PREWARM is off by default. Best-effort; never blocks the tick on failure."""
    try:
        import tiles
        lat, lon = last_known.get("lat"), last_known.get("lon")
        if lat is None or lon is None:
            return
        z = tiles.speed_to_zoom(last_known.get("speed_kmh"))
        tiles.basemap((lat, lon), z, int(os.environ.get("MAP_W", "1920")),
                      int(os.environ.get("MAP_H", "1080")))
    except Exception as e:  # noqa: BLE001
        print("prewarm skipped (%s)" % e)


def main():
    first_ts = int(time.time())
    prev = _read_json(NAV_STATE_JSON, {}) or {}
    last_write_ts = int(prev.get("ts") or 0)
    print("nav-tick up: interval=%ss prewarm=%s -> %s"
          % (NAV_TICK_INTERVAL_S, NAV_PREWARM, NAV_STATE_JSON))
    while True:
        try:
            fix = read_fix(GPSD_HOST, GPSD_PORT)
        except Exception as e:  # noqa: BLE001 — a transient gpsd error must not kill the daemon
            print("gpsd read failed (%s)" % e)
            fix = {"fix": False, "lat": None, "lon": None}
        new = navstate.compute_nav(prev, fix, time.time(), first_ts)
        if navstate.should_write(prev, new, last_write_ts, NAV_MOVE_WRITE_M, NAV_HEALTHY_WRITE_S):
            _atomic_write_json(NAV_STATE_JSON, new)
            last_write_ts = new["ts"]
        prev = new
        if NAV_PREWARM and new.get("fix"):
            _prewarm(new.get("lastKnown") or {})
        time.sleep(NAV_TICK_INTERVAL_S)


if __name__ == "__main__":
    sys.exit(main())
