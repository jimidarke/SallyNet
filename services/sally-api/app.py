#!/usr/bin/env python3
"""sally-api — the single HTTP surface the Roku dashboard polls.

Phase 0: live `/api/state` from gpsd + `/api/health` + `/api/discovery` (stub).
Sensor sections (power/tanks/env/level/cameras/audio) are `null` placeholders until
later phases fill them via the MQTT collector / go2rtc. Runs on its own port (:8090)
so it never touches the existing :80 metrics app.
"""
import math
import subprocess
import time

from flask import Flask, jsonify

import sallyconf as cfg
from gpsd_client import read_fix

app = Flask(__name__)
_BOOT = time.time()


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _throttled():
    try:
        out = subprocess.check_output(["vcgencmd", "get_throttled"], timeout=2)
        return out.decode().strip().split("=")[-1]
    except Exception:
        return None


def _prune(obj):
    """Recursively drop None so /api/state never emits JSON null. The Roku stores
    state in SceneGraph assocarray fields, which mishandle `invalid` values; omitting
    keys (the Roku reads a missing key back as invalid -> widget hidden) keeps the
    cross-thread round-trip clean. Empty lists/dicts are preserved."""
    if isinstance(obj, dict):
        return {k: _prune(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_prune(v) for v in obj]
    return obj


def _derive_mode(gps, km_from_home):
    if not gps["fix"]:
        return "unknown"
    if (gps["speed_kmh"] or 0) >= cfg.DRIVING_KMH:
        return "driving"
    if km_from_home is not None and km_from_home * 1000.0 <= cfg.HOME_RADIUS_M:
        return "at_home"
    return "parked"


@app.route("/api/state")
def api_state():
    gps = read_fix(cfg.GPSD_HOST, cfg.GPSD_PORT)
    km_from_home = None
    if gps["fix"] and gps["lat"] is not None:
        km_from_home = round(
            _haversine_km(gps["lat"], gps["lon"], cfg.HOME_LAT, cfg.HOME_LON), 1
        )
    payload = {
        "schemaVersion": cfg.SCHEMA_VERSION,
        "ts": int(time.time()),
        "mode": _derive_mode(gps, km_from_home),
        "gps": gps,
        "drive": {
            "odo_km": None,
            "trip_km": None,
            "km_from_home": km_from_home,
            "reverse": False,
        },
        "power": None,    # P2 — MQTT collector
        "tanks": None,    # P2
        "env": None,      # P2
        "level": None,    # P2
        "cameras": None,  # P3 — go2rtc /api/discovery
        "audio": None,    # P4
        "alerts": [],
        "system": {
            "host": cfg.HOSTNAME,
            "uptime_s": int(time.time() - _BOOT),
            "throttled": _throttled(),
        },
    }
    return jsonify(_prune(payload))


@app.route("/api/discovery")
def api_discovery():
    # Phase 3 fills `streams` from go2rtc on the N100. Empty for now.
    return jsonify({"schemaVersion": 1, "host": cfg.HOSTNAME, "streams": {}})


@app.route("/api/health")
def api_health():
    gps = read_fix(cfg.GPSD_HOST, cfg.GPSD_PORT, window=1.5)
    return jsonify({"ok": True, "gps_fix": gps["fix"], "ts": int(time.time())})


@app.route("/")
def index():
    return jsonify({
        "service": "sally-api",
        "schemaVersion": cfg.SCHEMA_VERSION,
        "endpoints": ["/api/state", "/api/discovery", "/api/health"],
    })


if __name__ == "__main__":
    app.run(host=cfg.HOST, port=cfg.PORT)
