#!/usr/bin/env python3
"""media-track-logger.py — append Sally's GPS position to a daily GPX breadcrumb log.

This is the one new always-on service the media pipeline needs: it records where Sally
has been so media that lacks embedded GPS can be geotagged by matching capture time to
a breadcrumb (see media-extract-meta.py, geotag fallback #2). Runs under its own systemd
unit (media-track-logger.service), polling gpsd every TRACK_INTERVAL_S seconds.

Writes one file per UTC day: <TRACKS_DIR>/<YYYY-MM-DD>.gpx, an open <trkseg> that we
append <trkpt> elements to (kept valid by closing the tags on each flush). Dependency-free
gpsd read mirrors services/sally-api/gpsd_client.py so this runs on EOL Buster unaided.

Env:
  TRACKS_DIR          where to write GPX        (default /mnt/usb/home/tracks)
  GPSD_HOST/GPSD_PORT gpsd endpoint             (default 127.0.0.1:2947)
  TRACK_INTERVAL_S    seconds between points    (default 15)
  TRACK_MIN_MOVE_M    skip points within N m of the last logged point (default 5)
"""
import json
import math
import os
import socket
import time
from datetime import datetime, timezone

TRACKS_DIR = os.environ.get("TRACKS_DIR", "/mnt/usb/home/tracks")
GPSD_HOST = os.environ.get("GPSD_HOST", "127.0.0.1")
GPSD_PORT = int(os.environ.get("GPSD_PORT", "2947"))
INTERVAL_S = float(os.environ.get("TRACK_INTERVAL_S", "15"))
MIN_MOVE_M = float(os.environ.get("TRACK_MIN_MOVE_M", "5"))

GPX_FOOTER = "  </trkseg>\n </trk>\n</gpx>\n"


def read_tpv(window=2.0):
    """Most recent gpsd TPV within `window` seconds, or {}. Mirrors gpsd_client."""
    tpv = {}
    try:
        sock = socket.create_connection((GPSD_HOST, GPSD_PORT), timeout=window)
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
            if obj.get("class") == "TPV":
                tpv = obj
        try:
            sock.sendall(b'?WATCH={"enable":false}\n')
        except OSError:
            pass
        sock.close()
    except OSError:
        pass
    return tpv


def _haversine_m(a, b):
    r = 6371008.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def gpx_path(now_utc):
    return os.path.join(TRACKS_DIR, now_utc.strftime("%Y-%m-%d") + ".gpx")


def ensure_header(path):
    """Create the day's GPX with header+footer if absent."""
    if os.path.exists(path):
        return
    head = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<gpx version="1.1" creator="sally-track-logger" '
            'xmlns="http://www.topografix.com/GPX/1/1">\n'
            ' <trk><name>Sally %s</name>\n  <trkseg>\n'
            % os.path.basename(path).replace(".gpx", ""))
    with open(path, "w") as f:
        f.write(head + GPX_FOOTER)


def append_point(path, lat, lon, alt, t_iso):
    """Insert a <trkpt> before the footer so the file stays valid after every write."""
    pt = '   <trkpt lat="%.7f" lon="%.7f">' % (lat, lon)
    if isinstance(alt, (int, float)):
        pt += "<ele>%.1f</ele>" % alt
    pt += "<time>%s</time></trkpt>\n" % t_iso
    with open(path, "r+") as f:
        data = f.read()
        idx = data.rfind(GPX_FOOTER)
        if idx < 0:  # footer missing (corrupt/truncated) — rebuild tail
            idx = len(data)
        f.seek(idx)
        f.write(pt + GPX_FOOTER)
        f.truncate()


def main():
    os.makedirs(TRACKS_DIR, exist_ok=True)
    last = None
    while True:
        tpv = read_tpv()
        mode = tpv.get("mode", 0) or 0
        lat, lon = tpv.get("lat"), tpv.get("lon")
        if mode >= 2 and isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            here = (lat, lon)
            if last is None or _haversine_m(last, here) >= MIN_MOVE_M:
                now = datetime.now(timezone.utc)
                path = gpx_path(now)
                try:
                    ensure_header(path)
                    t_iso = tpv.get("time") or now.strftime("%Y-%m-%dT%H:%M:%SZ")
                    append_point(path, lat, lon, tpv.get("alt"), t_iso)
                    last = here
                except OSError:
                    pass  # media disk not mounted / write error — try again next tick
        time.sleep(INTERVAL_S)


if __name__ == "__main__":
    main()
