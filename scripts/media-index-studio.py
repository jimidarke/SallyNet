#!/usr/bin/env python3
"""media-index-studio.py — indexes the Movies studio library (Workstream A, Phase 1).

Scans STUDIO_ROOT/movies/<Title (Year)>/... and atomic-writes movies.json, the read-model
sally-api's /api/media?type=movies serves. Deliberately separate from media-reindex.py
(Trips) — different root, different systemd timer — so a studio re-scan can never touch
the Trips pipeline. TV support (scan_tv, tv.json) lands in a later phase.

The pure scan/group logic lives in the importable sally-api `studio_index` module
(unit-tested off the Pi in test_studio_index.py); this script is just the CLI + atomic
write. Stdlib-only so it runs on the Pi's EOL Buster.

Env (all overridable):
  SALLY_API_DIR   deployed app dir      (default /opt/sally/sally-api) — for the import
  STUDIO_ROOT     studio library root   (default /mnt/usb)
  MOVIES_JSON     movies read-model out (default /var/lib/sally/movies.json)
"""
import os
import sys

sys.path.insert(0, os.environ.get("SALLY_API_DIR", "/opt/sally/sally-api"))
try:
    import store
    import studio_index
except Exception as e:  # noqa: BLE001 — degrade, don't crash-loop the service
    print("cannot import sally-api store/studio_index (%s) — exiting" % e)
    sys.exit(0)

STUDIO_ROOT = os.environ.get("STUDIO_ROOT", "/mnt/usb")
MOVIES_JSON = os.environ.get("MOVIES_JSON", "/var/lib/sally/movies.json")


def main():
    movies = studio_index.scan_movies(STUDIO_ROOT)
    catalog = studio_index.build_movie_categories(movies)
    store.atomic_write_json(MOVIES_JSON, catalog)
    print("media-index-studio: %d movies -> %s" % (len(movies), MOVIES_JSON))


if __name__ == "__main__":
    main()
