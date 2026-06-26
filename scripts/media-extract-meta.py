#!/usr/bin/env python3
"""media-extract-meta.py — read capture metadata from a source media file and write
a SallyNet catalog sidecar.

Responsibilities:
  * Pull capture datetime, embedded GPS, camera make/model, dimensions and duration
    out of the *original* via exiftool.
  * Resolve a geotag with the locked fallback chain:
        1. embedded GPS in the file            -> gps.source = "embedded"
        2. correlate capture time to a GPX      -> gps.source = "track"
           breadcrumb (nearest point <= window)
        3. none                                 -> gps omitted entirely
  * Merge the post-encode fields the ingest worker injects via --set
    (id, type, collection.*, mediaPath, posterPath, codec, container, durationSec,
    width, height, fps, fileSizeBytes, sha256, uploader, ingestDatetime ...).
  * Emit the sidecar JSON (to --out or stdout). Follows the omit-not-null rule:
    keys whose value is None are dropped.

Stdlib only — the Pi is EOL Buster (Python 3.7, no zoneinfo). Timezones are handled
with fixed offsets: a tz-aware capture time is honored; a naive one is assumed to be
in the camper's local offset (--local-utc-offset, default -6 / Mountain). Not DST-aware;
this only affects the track-correlation fallback, and most phone media carries its own GPS.

Usage:
  media-extract-meta.py <src> [--tracks-dir D] [--window-sec N]
                         [--local-utc-offset H] [--set k=v ...] [--out FILE]
"""
import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

DRONE_HINTS = ("dji", "mavic", "phantom", "autel", "skydio", "parrot", "anafi")


def run_exiftool(src):
    """Return exiftool's tag dict (numeric values), or {} on any failure."""
    try:
        out = subprocess.check_output(
            ["exiftool", "-j", "-n", "-api", "QuickTimeUTC=1", src],
            stderr=subprocess.DEVNULL, timeout=60,
        )
        data = json.loads(out.decode("utf-8", "replace"))
        return data[0] if data else {}
    except Exception:
        return {}


def _parse_dt(s, default_offset_h):
    """Parse an exiftool datetime string to a tz-aware datetime, or None.

    Accepts 'YYYY:MM:DD HH:MM:SS', optional fractional seconds, optional trailing
    offset ('Z', '+HH:MM', '-HH:MM'). Naive values get the configured local offset.
    """
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    tz = None
    # Split a trailing offset / Z, if present.
    if s.endswith("Z"):
        tz = timezone.utc
        s = s[:-1].strip()
    else:
        if len(s) >= 6 and s[-6] in "+-" and s[-3] == ":":
            sign = 1 if s[-6] == "+" else -1
            oh, om = int(s[-5:-3]), int(s[-2:])
            tz = timezone(sign * timedelta(hours=oh, minutes=om))
            s = s[:-6].strip()
    s = s.split(".")[0]  # drop fractional seconds
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            break
        except ValueError:
            dt = None
    if dt is None:
        return None
    if tz is None:
        tz = timezone(timedelta(hours=default_offset_h))
    return dt.replace(tzinfo=tz)


def capture_datetime(tags, src, default_offset_h):
    """Best capture time: SubSec/DateTimeOriginal > CreateDate > Track/Media create
    > file mtime. Returns a tz-aware datetime."""
    for key in ("SubSecDateTimeOriginal", "DateTimeOriginal", "CreateDate",
                "CreationDate", "MediaCreateDate", "TrackCreateDate"):
        dt = _parse_dt(tags.get(key), default_offset_h)
        # Reject implausible values — e.g. the QuickTime zero-epoch (1904) that ffmpeg
        # writes when a source has no real creation_time; fall through to file mtime.
        if dt and dt.year >= 1990:
            return dt
    # Fall back to file modification time.
    try:
        mt = datetime.fromtimestamp(os.path.getmtime(src),
                                    tz=timezone(timedelta(hours=default_offset_h)))
        return mt
    except OSError:
        return datetime.now(timezone(timedelta(hours=default_offset_h)))


def embedded_gps(tags):
    """Signed decimal (lat, lon) from exiftool Composite GPS, or None."""
    lat = tags.get("GPSLatitude")
    lon = tags.get("GPSLongitude")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        # With -n exiftool usually emits signed composite values; guard the rare
        # unsigned case using the ref tags.
        if tags.get("GPSLatitudeRef") in ("S", "South") and lat > 0:
            lat = -lat
        if tags.get("GPSLongitudeRef") in ("W", "West") and lon > 0:
            lon = -lon
        if lat == 0 and lon == 0:
            return None
        return (round(float(lat), 7), round(float(lon), 7))
    return None


def _iter_gpx_points(path):
    """Yield (epoch_utc, lat, lon) for each trackpoint with a timestamp."""
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError):
        return
    for el in tree.iter():
        tag = el.tag.rsplit("}", 1)[-1]  # strip namespace
        if tag != "trkpt" and tag != "wpt":
            continue
        try:
            lat = float(el.get("lat"))
            lon = float(el.get("lon"))
        except (TypeError, ValueError):
            continue
        t = None
        for child in el:
            if child.tag.rsplit("}", 1)[-1] == "time" and child.text:
                t = child.text.strip()
                break
        if not t:
            continue
        dt = _parse_dt(t, 0)  # GPX time is ISO 'YYYY-MM-DDTHH:MM:SSZ' (UTC)
        if dt is None:
            continue
        yield (dt.timestamp(), lat, lon)


def correlate_track(capture_dt, tracks_dir, window_sec):
    """Nearest breadcrumb (lat, lon) to capture_dt across all GPX in tracks_dir,
    if within window_sec. Returns (lat, lon) or None."""
    if not tracks_dir or not os.path.isdir(tracks_dir):
        return None
    target = capture_dt.astimezone(timezone.utc).timestamp()
    best = None
    best_dt = window_sec + 1
    for gpx in sorted(glob.glob(os.path.join(tracks_dir, "*.gpx"))):
        for epoch, lat, lon in _iter_gpx_points(gpx):
            d = abs(epoch - target)
            if d < best_dt:
                best_dt = d
                best = (round(lat, 7), round(lon, 7))
    return best if best_dt <= window_sec else None


def _coerce(v):
    """Type-infer a --set value: int, float, true/false/null, else string."""
    if v == "true":
        return True
    if v == "false":
        return False
    if v == "null" or v == "":
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def _set_dotted(d, dotted, value):
    keys = dotted.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def prune(obj):
    if isinstance(obj, dict):
        return {k: prune(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [prune(v) for v in obj]
    return obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--tracks-dir")
    ap.add_argument("--window-sec", type=int, default=120)
    ap.add_argument("--local-utc-offset", type=float,
                    default=float(os.environ.get("MEDIA_LOCAL_UTC_OFFSET", "-6")))
    ap.add_argument("--set", action="append", default=[], metavar="k=v",
                    help="merge post-encode field (dot notation, type-inferred)")
    ap.add_argument("--out")
    args = ap.parse_args()

    tags = run_exiftool(args.src)
    cap = capture_datetime(tags, args.src, args.local_utc_offset)

    make = tags.get("Make") or ""
    model = tags.get("Model") or ""
    blob = (str(make) + " " + str(model) + " " + os.path.basename(args.src)).lower()
    is_drone = any(h in blob for h in DRONE_HINTS)

    sidecar = {
        "schemaVersion": 1,
        "captureDatetime": cap.isoformat(),
        "cameraMake": str(make) or None,
        "cameraModel": str(model) or None,
        "isDrone": is_drone or None,
    }

    # Geotag chain: embedded -> track -> omit.
    gps = embedded_gps(tags)
    if gps:
        sidecar["gps"] = {"lat": gps[0], "lon": gps[1], "source": "embedded"}
    else:
        tp = correlate_track(cap, args.tracks_dir, args.window_sec)
        if tp:
            sidecar["gps"] = {"lat": tp[0], "lon": tp[1], "source": "track"}

    # Source dims/duration (the worker usually overrides with post-encode values).
    w = tags.get("ImageWidth") or tags.get("SourceImageWidth")
    h = tags.get("ImageHeight") or tags.get("SourceImageHeight")
    if isinstance(w, int):
        sidecar["width"] = w
    if isinstance(h, int):
        sidecar["height"] = h
    dur = tags.get("Duration") or tags.get("MediaDuration") or tags.get("TrackDuration")
    if isinstance(dur, (int, float)):
        sidecar["durationSec"] = round(float(dur), 1)

    # Merge injected fields (override extraction where keys collide).
    for kv in args.set:
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        _set_dotted(sidecar, k, _coerce(v))

    out = json.dumps(prune(sidecar), indent=2, sort_keys=True)
    if args.out:
        tmp = args.out + ".tmp"
        with open(tmp, "w") as f:
            f.write(out + "\n")
        os.replace(tmp, args.out)  # atomic publish
    else:
        print(out)


if __name__ == "__main__":
    sys.exit(main())
