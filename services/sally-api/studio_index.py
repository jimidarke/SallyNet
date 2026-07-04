"""Pure filesystem-scan + grouping logic for the Movies/TV studio library — independently
unit-tested off the Pi (see test_studio_index.py), same shape as navstate.py.

Movies live at <studio_root>/movies/<Title (Year)>/<Title (Year)>.mp4 — one file per
folder, confirmed live on campingpi. scan_movies() only ever looks at that one root; the
Flask layer (app.py) owns turning its output into the frozen /api/media response shape.

build_movie_categories() turns the flat scan into Netflix-style curated rows (Recently
Added, Kids & Family, genre rows, All Movies). Genre/poster/kidSafe enrichment comes from
the TMDB art index (studio_art.py) + hand overrides (studio-overrides.json); with neither,
it degrades to Recently Added + All Movies — still valid, still fully offline.
"""
import os
import re
import urllib.parse

import store

_MOVIE_FOLDER_RE = re.compile(r"^(.+?)\s*\((\d{4})\)$")

_VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".m4v")

# How many of the newest movies/shows (by folder mtime) the "Recently Added" row shows.
_RECENT_N = 20

# TV episodes must be Roku-playable to enter the model — a pending (un-re-encoded) .mkv is
# hidden "for free", so the whole UI ships safely against a half-transferred tv/ tree.
_TV_EXTS = (".mp4", ".m4v")
_SEASON_RE = re.compile(r"(?i)^season\s+(\d{1,2})$")
_EP_RE = re.compile(r"(?i)s(\d{1,2})e(\d{1,3})")
_EP_LOOSE_RE = re.compile(r"(?<!\d)(\d{1,2})x(\d{1,3})(?!\d)")


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
    """List of {id, title, year, relpath, mtime} for every well-formed movie folder that
    actually contains a video file. relpath is relative to studio_root (what
    /media/<relpath> serves), e.g. "movies/Cars (2006)/Cars (2006).mp4"; mtime is the
    folder mtime (drives the offline "Recently Added" row)."""
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
            "mtime": os.path.getmtime(folder_path),
        })
    out.sort(key=lambda m: m["title"].lower())
    return out


def _movie_item(m, enriched=None):
    # Movie filenames are human/release-style ("20,000 Leagues Under the Sea (1954).mp4"),
    # unlike Trips' pipeline-generated ASCII-safe names — unencoded spaces/commas/parens
    # break the Roku's HTTP fetch outright (confirmed live: the raw path gets no response
    # at all, vs 206 once encoded). safe="/" keeps the path structure intact.
    url = "/media/" + urllib.parse.quote(m["relpath"], safe="/")
    item = {"id": m["id"], "type": "video", "title": m["title"], "url": url, "year": m["year"]}
    if enriched:
        # Additive per the frozen contract; each key OMITTED when unknown (omit-not-null).
        # kidSafe is emitted ONLY when truly true — _prune keeps False, which would wrongly
        # light the KIDS badge (see MediaCard.brs and app.py _prune).
        if enriched.get("poster"):
            item["poster"] = enriched["poster"]
        if enriched.get("genres"):
            item["genres"] = list(enriched["genres"])
        if enriched.get("kidSafe") is True:
            item["kidSafe"] = True
    return item


# Presentation fields a hand override may force (applied at build time, no network).
# Match fields (tmdbId/title/year) live in the same override file but are consumed by the
# fetcher (studio_art.py), not here.
_OVERRIDE_PRESENTATION_KEYS = ("poster", "genres", "kidSafe")


def _enrich(m, art, overrides):
    """Merge the TMDB art record and the hand override for one movie.
    Precedence: override > art > {} (override wins)."""
    rec = {}
    if art:
        rec.update(art.get(m["id"]) or {})
    if overrides:
        ov = (overrides.get("movies") or {}).get(m["id"])
        if ov:
            for k in _OVERRIDE_PRESENTATION_KEYS:
                if k in ov:
                    rec[k] = ov[k]
    return rec


def build_movie_categories(movies, art=None, overrides=None):
    """Trips-catalog-shaped {collections, items}: a metadata list + an items dict keyed by
    category id, so /api/collections/<catId> resolves each row unchanged. Rows, in render
    order: Recently Added -> Kids & Family -> genre rows (by count desc) -> All Movies
    (always present, even empty, as the catch-all pane). More/other rows are a pure
    server-side change — the Roku RowList renders however many the server sends."""
    enriched = {m["id"]: _enrich(m, art, overrides) for m in movies}
    item_of = {m["id"]: _movie_item(m, enriched[m["id"]]) for m in movies}

    collections = []
    items = {}

    def add_row(cid, title, movie_list):
        if not movie_list:
            return
        its = [item_of[mm["id"]] for mm in movie_list]
        collections.append({
            "id": cid, "kind": "category", "title": title,
            "itemCount": len(its), "detailUrl": "/api/collections/" + cid,
        })
        items[cid] = its

    # 1. Recently Added — newest folders first (offline; no TMDB needed).
    recent = sorted(movies, key=lambda mm: mm.get("mtime", 0), reverse=True)[:_RECENT_N]
    add_row("recently-added", "Recently Added", recent)

    # 2. Kids & Family — the per-item kidSafe flag (override- or heuristic-driven).
    kids = [mm for mm in movies if enriched[mm["id"]].get("kidSafe") is True]
    add_row("kids-family", "Kids & Family", kids)

    # 3. Genre rows — one per genre present, ordered by movie count desc then name.
    by_genre = {}
    for mm in movies:
        for g in (enriched[mm["id"]].get("genres") or []):
            by_genre.setdefault(g, []).append(mm)
    for name, mlist in sorted(by_genre.items(), key=lambda kv: (-len(kv[1]), kv[0].lower())):
        add_row("genre-" + store.slug(name), name, mlist)

    # 4. All Movies — always present (even with zero metadata), guarantees a non-empty pane.
    all_items = [item_of[m["id"]] for m in movies]
    collections.append({
        "id": "all", "kind": "category", "title": "All Movies",
        "itemCount": len(all_items), "detailUrl": "/api/collections/all",
    })
    items["all"] = all_items

    return {"collections": collections, "items": items}


# =============================================================================
# TV Shows — mirrors Movies, adding a show -> season -> episode hierarchy. Layout:
#   tv/<Show (Year)>/Season NN/<Show> - SxxEyy - <Title>.mp4   (year + season folder optional)
# Only .mp4/.m4v episodes enter the model; ids are composite + resume-friendly.
# =============================================================================

def parse_show_folder(name):
    """'Bluey (2018)' -> ('Bluey', '2018'); 'The Office' -> ('The Office', None)."""
    m = _MOVIE_FOLDER_RE.match(name)
    if m:
        return m.group(1), m.group(2)
    return name, None


def parse_season_folder(name):
    """'Season 01' -> 1, 'Specials' -> 0, anything else -> None."""
    if name.strip().lower() == "specials":
        return 0
    m = _SEASON_RE.match(name.strip())
    return int(m.group(1)) if m else None


def parse_episode(filename):
    """'Bluey - S01E03 - Daddy Robot.mp4' -> (1, 3, 'Daddy Robot'). Authoritative SxxEyy,
    loose NxN fallback; title is the text after the token (or None). None if no match."""
    stem = filename
    dot = stem.rfind(".")
    if dot > 0:
        stem = stem[:dot]
    m = _EP_RE.search(stem) or _EP_LOOSE_RE.search(stem)
    if not m:
        return None
    season, episode = int(m.group(1)), int(m.group(2))
    title = re.sub(r"\s+", " ", stem[m.end():].strip(" -_.")).strip()
    return (season, episode, title or None)


def scan_tv(studio_root):
    """List of show dicts {id,title,year,relroot,mtime,seasons:[{season,id,episodes:[...]}]}
    for every show folder with at least one playable episode. Composite ids: show
    'slug-year', season 'slug-year-sNN', episode 'slug-year-sNNeMM' (the episode id is the
    VodPlayer contentid, so per-episode resume works for free)."""
    tv_dir = os.path.join(studio_root, "tv")
    try:
        show_folders = sorted(os.listdir(tv_dir))
    except OSError:
        return []
    shows = []
    for sf in show_folders:
        show_path = os.path.join(tv_dir, sf)
        if not os.path.isdir(show_path):
            continue
        title, year = parse_show_folder(sf)
        show_id = store.slug(title) + (("-" + year) if year else "")
        seasons_map = {}
        for root, _dirs, files in os.walk(show_path):
            for fn in sorted(files):
                if not fn.lower().endswith(_TV_EXTS):
                    continue
                parsed = parse_episode(fn)
                if not parsed:
                    continue
                snum, enum, etitle = parsed
                relpath = os.path.relpath(os.path.join(root, fn), studio_root).replace(os.sep, "/")
                seasons_map.setdefault(snum, {})[enum] = {
                    "id": "%s-s%02de%02d" % (show_id, snum, enum),
                    "season": snum, "episode": enum, "title": etitle, "relpath": relpath,
                }
        if not seasons_map:
            continue    # no playable episodes -> hide the show entirely
        seasons = []
        for snum in sorted(seasons_map.keys()):
            eps = [seasons_map[snum][e] for e in sorted(seasons_map[snum].keys())]
            seasons.append({"season": snum, "id": "%s-s%02d" % (show_id, snum), "episodes": eps})
        shows.append({"id": show_id, "title": title, "year": year,
                      "relroot": "tv/" + sf, "seasons": seasons,
                      "mtime": os.path.getmtime(show_path)})
    shows.sort(key=lambda s: s["title"].lower())
    return shows


def _enrich_show(s, art, overrides):
    rec = {}
    if art:
        rec.update((art.get("shows") or {}).get(s["id"]) or {})
    if overrides:
        ov = (overrides.get("shows") or {}).get(s["id"])
        if ov:
            for k in ("poster", "genres", "kidSafe", "overview"):
                if k in ov:
                    rec[k] = ov[k]
    return rec


def _episode_enrich(ep_id, art, overrides):
    rec = {}
    if art:
        rec.update((art.get("episodes") or {}).get(ep_id) or {})
    if overrides:
        ov = (overrides.get("episodes") or {}).get(ep_id)
        if ov:
            for k in ("still", "title", "overview", "durationSec", "kidSafe"):
                if k in ov:
                    rec[k] = ov[k]
    return rec


def _season_label(n):
    return "Specials" if n == 0 else ("Season " + str(n))


def _show_card(s, enriched):
    card = {"id": s["id"], "type": "show", "title": s["title"],
            "seasonCount": len(s["seasons"]),
            "episodeCount": sum(len(se["episodes"]) for se in s["seasons"]),
            "detailUrl": "/api/show/" + s["id"]}
    if s.get("year"):
        card["year"] = s["year"]
    if enriched.get("poster"):
        card["poster"] = enriched["poster"]
    if enriched.get("kidSafe") is True:
        card["kidSafe"] = True
    return card


def _show_detail(s, enriched, art, overrides):
    d = {"id": s["id"], "kind": "show", "title": s["title"], "seasons": []}
    if s.get("year"):
        d["year"] = s["year"]
    if enriched.get("poster"):
        d["poster"] = enriched["poster"]
    if enriched.get("overview"):
        d["overview"] = enriched["overview"]
    if enriched.get("kidSafe") is True:
        d["kidSafe"] = True
    for se in s["seasons"]:
        season = {"season": se["season"], "id": se["id"],
                  "title": _season_label(se["season"]),
                  "episodeCount": len(se["episodes"]), "episodes": []}
        for ep in se["episodes"]:
            item = {"id": ep["id"], "type": "video", "season": ep["season"],
                    "episode": ep["episode"],
                    "url": "/media/" + urllib.parse.quote(ep["relpath"], safe="/")}
            if ep.get("title"):
                item["title"] = ep["title"]
            en = _episode_enrich(ep["id"], art, overrides)
            if en.get("title"):
                item["title"] = en["title"]
            if en.get("still"):
                item["still"] = en["still"]
            if en.get("overview"):
                item["overview"] = en["overview"]
            if en.get("durationSec"):
                item["durationSec"] = en["durationSec"]
            if en.get("kidSafe") is True:
                item["kidSafe"] = True
            season["episodes"].append(item)
        d["seasons"].append(season)
    return d


def build_tv_read_model(shows, art=None, overrides=None):
    """{collections, items, shows}: genre/curated rows of SHOW cards (items, keyed by
    category id — 'tv-*' namespaced so they never collide with movies' bare ids) plus a
    shows map of full season/episode detail (served by /api/show/<id>). Empty shows ->
    reserved-empty {collections:[]} (today's type=tv response), so the UI ships safely."""
    enriched = {s["id"]: _enrich_show(s, art, overrides) for s in shows}
    card_of = {s["id"]: _show_card(s, enriched[s["id"]]) for s in shows}

    collections = []
    items = {}

    def add_row(cid, title, show_list):
        if not show_list:
            return
        cards = [card_of[s["id"]] for s in show_list]
        collections.append({"id": cid, "kind": "category", "title": title,
                            "itemCount": len(cards), "detailUrl": "/api/collections/" + cid})
        items[cid] = cards

    recent = sorted(shows, key=lambda s: s.get("mtime", 0), reverse=True)[:_RECENT_N]
    add_row("tv-recently-added", "Recently Added", recent)
    kids = [s for s in shows if enriched[s["id"]].get("kidSafe") is True]
    add_row("tv-kids-family", "Kids & Family", kids)
    by_genre = {}
    for s in shows:
        for g in (enriched[s["id"]].get("genres") or []):
            by_genre.setdefault(g, []).append(s)
    for name, slist in sorted(by_genre.items(), key=lambda kv: (-len(kv[1]), kv[0].lower())):
        add_row("tv-genre-" + store.slug(name), name, slist)
    add_row("tv-all", "All Shows", shows)   # last; skipped when there are no shows

    return {"collections": collections, "items": items,
            "shows": {s["id"]: _show_detail(s, enriched[s["id"]], art, overrides) for s in shows}}
