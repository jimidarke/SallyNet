"""Minimal read-only gpsd client over the JSON protocol — no external deps.

Connects to gpsd, enables a JSON watch, reads a short burst, and returns the most
recent TPV (position/velocity) merged with the most recent SKY (satellites/DOP).
Kept dependency-free on purpose: EOL Buster has no `python3-gps`, and a ~40-line
socket reader is more robust than fighting pip on an archived distro.
"""
import json
import socket
import time


def _read_burst(host, port, window):
    """Return (latest_tpv, latest_sky) seen within `window` seconds."""
    tpv, sky = {}, {}
    try:
        sock = socket.create_connection((host, port), timeout=window)
        sock.settimeout(window)
        sock.sendall(b'?WATCH={"enable":true,"json":true}\n')
        stream = sock.makefile("r")
        deadline = time.time() + window
        while time.time() < deadline:
            line = stream.readline()
            if not line:
                break
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            cls = obj.get("class")
            if cls == "TPV":
                tpv = obj
            elif cls == "SKY":
                sky = obj
        try:
            sock.sendall(b'?WATCH={"enable":false}\n')
        except OSError:
            pass
        sock.close()
    except OSError:
        pass
    return tpv, sky


def read_fix(host="127.0.0.1", port=2947, window=2.5):
    """Return a normalized fix dict (keys always present; values None when no fix)."""
    tpv, sky = _read_burst(host, port, window)
    mode = tpv.get("mode", 0) or 0
    speed_ms = tpv.get("speed")
    alt = tpv.get("alt", tpv.get("altMSL"))
    sats = sky.get("satellites") or []
    used = sum(1 for s in sats if s.get("used"))
    return {
        "fix": mode >= 2,
        "mode": mode,
        "lat": tpv.get("lat"),
        "lon": tpv.get("lon"),
        "speed_kmh": round(speed_ms * 3.6, 1) if isinstance(speed_ms, (int, float)) else None,
        "heading": tpv.get("track"),
        "alt_m": round(alt, 1) if isinstance(alt, (int, float)) else None,
        "sats": used,
        "sats_visible": len(sats),
        "hdop": sky.get("hdop"),
        "time": tpv.get("time"),
    }
