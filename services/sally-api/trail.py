"""trail.py — read today's GPS breadcrumb for the map's trail layer.

scripts/media-track-logger.py appends one daily GPX file (YYYY-MM-DD.gpx, UTC) per the
running track. TrailCache parses today's file into a list of (lat, lon) points for the
compositor, re-reading only when the file's mtime changes (the logger appends as Sally moves)
and downsampling very long days so the polyline stays cheap to project + draw on the Pi.
"""
import os
import re
import time

# The logger writes one <trkpt lat=".." lon=".."> per point; findall keeps file (chronological)
# order. Regex over the text avoids GPX-namespace handling for a fixed, self-produced format.
_TRKPT_RE = re.compile(r'<trkpt\s+lat="([-\d.]+)"\s+lon="([-\d.]+)"')


def today_gpx_path(tracks_dir, now=None):
    """Path to today's GPX file (UTC date, matching the logger's naming)."""
    t = time.gmtime(now) if now is not None else time.gmtime()
    return os.path.join(tracks_dir, time.strftime("%Y-%m-%d", t) + ".gpx")


def _iter_gpx_points(path):
    """All (lat, lon) trackpoints in `path`, in file order. [] on any read error."""
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return []
    return [(float(a), float(b)) for a, b in _TRKPT_RE.findall(text)]


def _downsample(pts, max_points):
    """Cap to ~max_points evenly, always keeping the first and the most-recent point."""
    n = len(pts)
    if max_points <= 0 or n <= max_points:
        return pts
    step = n / float(max_points)
    out = [pts[int(i * step)] for i in range(max_points)]
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return out


class TrailCache:
    """Today's breadcrumb points, re-parsed only when the day's GPX file changes."""

    def __init__(self, tracks_dir, max_points=1500):
        self._dir = tracks_dir
        self._max = max_points
        self._path = None
        self._mtime = -1.0
        self._pts = []

    def get(self, now=None):
        path = today_gpx_path(self._dir, now)
        try:
            mtime = os.stat(path).st_mtime
        except OSError:
            # No track logged yet today (or tracks dir absent) -> empty trail.
            self._path, self._mtime, self._pts = path, -1.0, []
            return self._pts
        if path != self._path or mtime != self._mtime:
            self._pts = _downsample(_iter_gpx_points(path), self._max)
            self._path, self._mtime = path, mtime
        return self._pts
