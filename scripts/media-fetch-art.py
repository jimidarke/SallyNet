#!/usr/bin/env python3
"""media-fetch-art.py — manually (re)fetch TMDB posters/genres for the studio library and
rebuild movies.json. The nightly path is media-index-studio.py (always incremental); use
this after editing studio-overrides.json, or to retry unmatched titles over LTE.

  media-fetch-art.py                  # incremental (same as nightly)
  media-fetch-art.py --force          # re-fetch ALL movies
  media-fetch-art.py --refresh <id>   # re-fetch just <id> (repeatable)

Shares studio_reindex with the nightly driver — one code path. Env: same as
media-index-studio.py (SALLY_API_DIR, STUDIO_ROOT, TMDB_*, STUDIO_ART_*, STUDIO_OVERRIDES).
"""
import os
import sys

sys.path.insert(0, os.environ.get("SALLY_API_DIR", "/opt/sally/sally-api"))
try:
    import sallyconf as cfg
    import studio_reindex
except Exception as e:  # noqa: BLE001
    print("cannot import sally-api store/studio modules (%s) — exiting" % e)
    sys.exit(0)


def main(argv):
    force_all = "--force" in argv
    force_ids = []
    i = 0
    while i < len(argv):
        if argv[i] == "--refresh" and i + 1 < len(argv):
            force_ids.append(argv[i + 1])
            i += 2
        else:
            i += 1
    movies, catalog = studio_reindex.reindex_movies(
        force_ids=force_ids or None, force_all=force_all)
    detail = ""
    if force_all:
        detail = " (forced all)"
    elif force_ids:
        detail = " (refresh %s)" % ",".join(force_ids)
    print("media-fetch-art: %d movies, %d rows -> %s%s" % (
        len(movies), len(catalog.get("collections", [])), cfg.MOVIES_JSON, detail))


if __name__ == "__main__":
    main(sys.argv[1:])
