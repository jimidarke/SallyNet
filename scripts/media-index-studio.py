#!/usr/bin/env python3
"""media-index-studio.py — nightly studio Movies re-index (Workstream A).

Scans STUDIO_ROOT/movies/<Title (Year)>/..., fetches TMDB posters/genres (incremental,
offline-safe), and atomic-writes movies.json — the read-model sally-api's
/api/media?type=movies serves. Deliberately separate from media-reindex.py (Trips) —
different root, different systemd timer — so a studio re-scan can never touch the Trips
pipeline.

The scan/categorize/TMDB logic lives in the importable, unit-tested sally-api modules
(studio_index + studio_art + studio_reindex); this script is just the nightly CLI.
Stdlib-only so it runs on the Pi's EOL Buster. No flags — nightly is always incremental
(the first populate hits TMDB, later runs skip cached movies); use media-fetch-art.py for
a forced re-fetch after editing overrides.

Env (all overridable, see sallyconf.py):
  SALLY_API_DIR   deployed app dir   (default /opt/sally/sally-api) — for the import
  STUDIO_ROOT, MOVIES_JSON, TMDB_* , STUDIO_ART_* , STUDIO_OVERRIDES
"""
import os
import sys

sys.path.insert(0, os.environ.get("SALLY_API_DIR", "/opt/sally/sally-api"))
try:
    import sallyconf as cfg
    import studio_reindex
except Exception as e:  # noqa: BLE001 — degrade, don't crash-loop the service
    print("cannot import sally-api store/studio modules (%s) — exiting" % e)
    sys.exit(0)


def main():
    movies, mcat = studio_reindex.reindex_movies()
    shows, tvmodel = studio_reindex.reindex_tv()
    print("media-index-studio: %d movies (%d rows) -> %s ; %d shows (%d rows) -> %s" % (
        len(movies), len(mcat.get("collections", [])), cfg.MOVIES_JSON,
        len(shows), len(tvmodel.get("collections", [])), cfg.TV_JSON))


if __name__ == "__main__":
    main()
