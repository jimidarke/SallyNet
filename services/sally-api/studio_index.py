"""Pure filesystem-scan + grouping logic for the Movies/TV studio library — independently
unit-tested off the Pi (see test_studio_index.py), same shape as navstate.py.

Movies live at <studio_root>/movies/<Title (Year)>/<Title (Year)>.mp4 — one file per
folder, confirmed live on campingpi. scan_movies() only ever looks at that one root; the
Flask layer (app.py) owns turning its output into the frozen /api/media response shape.
"""
import os
import re
import urllib.parse

import store

_MOVIE_FOLDER_RE = re.compile(r"^(.+?)\s*\((\d{4})\)$")

_VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".m4v")


def parse_movie_folder(name):
    """'Cars (2006)' -> ('Cars', '2006'); anything not matching 'Title (YYYY)' -> None."""
    m = _MOVIE_FOLDER_RE.match(name)
    if not m:
        return None
    return m.group(1), m.group(2)


def _find_video_file(dirpath):
    """First video file directly inside dirpath, or None."""
    try:
        entries = sorted(os.listdir(dirpath))
    except OSError:
        return None
    for entry in entries:
        if entry.lower().endswith(_VIDEO_EXTS):
            return entry
    return None


def scan_movies(studio_root):
    """List of {id, title, year, relpath} for every well-formed movie folder that
    actually contains a video file. relpath is relative to studio_root (what
    /media/<relpath> serves), e.g. "movies/Cars (2006)/Cars (2006).mp4"."""
    movies_dir = os.path.join(studio_root, "movies")
    try:
        folders = sorted(os.listdir(movies_dir))
    except OSError:
        return []
    out = []
    for folder in folders:
        folder_path = os.path.join(movies_dir, folder)
        if not os.path.isdir(folder_path):
            continue
        parsed = parse_movie_folder(folder)
        if not parsed:
            continue
        title, year = parsed
        video = _find_video_file(folder_path)
        if not video:
            continue
        out.append({
            "id": store.slug(title) + "-" + year,
            "title": title,
            "year": year,
            "relpath": "movies/" + folder + "/" + video,
        })
    out.sort(key=lambda m: m["title"].lower())
    return out


def _movie_item(m):
    # Movie filenames are human/release-style ("20,000 Leagues Under the Sea (1954).mp4"),
    # unlike Trips' pipeline-generated ASCII-safe names — unencoded spaces/commas/parens
    # break the Roku's HTTP fetch outright (confirmed live: the raw path gets no response
    # at all, vs 206 once encoded). safe="/" keeps the path structure intact.
    url = "/media/" + urllib.parse.quote(m["relpath"], safe="/")
    return {"id": m["id"], "type": "video", "title": m["title"], "url": url, "year": m["year"]}


def build_movie_categories(movies):
    """Trips-catalog-shaped {collections, items}: a metadata list + an items dict keyed
    by category id. Phase 1 emits a single 'All Movies' category; once kidSafe/genre
    data exists (Phase 4 overrides + TMDB) more categories can be added here with no
    Roku-side change needed — RowList already renders however many rows the server sends."""
    items = [_movie_item(m) for m in movies]
    return {
        "collections": [{
            "id": "all", "kind": "category", "title": "All Movies",
            "itemCount": len(items), "detailUrl": "/api/collections/all",
        }],
        "items": {"all": items},
    }
