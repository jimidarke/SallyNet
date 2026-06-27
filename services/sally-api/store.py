"""Small JSON read-model store for sally-api — atomic writes + mtime-cached reads.

Mirrors the pattern proven in scripts/media-reindex.py (flock + .tmp + os.replace for
writers) and app.py:_load_catalog (per-request mtime check for readers). Used by the
trip store, the OSRM route cache, and the fuel log so a concurrent writer (a POST
handler, the ETA refresher) and the 5 s /api/state poll never see a half-written file.

Everything lives on the Pi's LOCAL disk (SD), never the bulky/disposable media disk.
"""
import fcntl
import json
import os
import re
import time


def slug(text):
    """Lowercase, collapse runs of non-alnum to a single '-', strip ends.

    Matches media-ingest.sh:slug so a trip created here lands on the SAME collection id
    the media pipeline routes uploads to.
    """
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower())
    return s.strip("-")


def atomic_write_json(path, data, indent=2):
    """Write `data` as JSON to `path` atomically under an flock. Creates parent dirs."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lock = path + ".lock"
    with open(lock, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=indent, sort_keys=True)
        os.replace(tmp, path)  # atomic
        fcntl.flock(lf, fcntl.LOCK_UN)


def read_json(path, default=None):
    """One-shot read; returns `default` on any error (missing / malformed)."""
    try:
        with open(path) as f:
            return json.load(f)
    except (ValueError, OSError):
        return default


class CachedJson:
    """Reader that reloads only when the file's mtime changes (cheap per-request).

    Construct one per file at import time; call .get() inside request handlers.
    """

    def __init__(self, path, default):
        self._path = path
        self._default = default
        self._mtime = -1.0
        self._data = default

    def get(self):
        try:
            mtime = os.stat(self._path).st_mtime
        except OSError:
            return self._data
        if mtime != self._mtime:
            loaded = read_json(self._path, None)
            if loaded is not None:
                self._data = loaded
                self._mtime = mtime
        return self._data

    def invalidate(self):
        """Force the next get() to re-read from disk. Call after writing the file from
        this same process — a back-to-back write can land on the same coarse mtime, so
        mtime alone could miss it."""
        self._mtime = -1.0


def now_s():
    return int(time.time())
