"""TMDB metadata + poster-artwork enrichment for the studio Movies/TV library.

Pure core (matching, genre mapping, url building, kid-safe heuristic) is unit-tested off
the Pi; the thin I/O (TmdbClient over urllib, poster download, ffmpeg frame-grab) is
injectable so refresh_art() can be tested with fakes. Stdlib-only — the Pi is on EOL
Buster with no `requests` (app.py:_geocode does the same over urllib).

refresh_art() is incremental and offline-safe: it skips movies already cached with a
poster on disk, and on any TMDB miss/timeout falls back to a frame-grab from the movie's
own file, so a fully-offline nightly run still produces valid art. The whole
STUDIO_ROOT/.art/ tree (posters + index.json) is one self-contained, disposable cache
unit — a disk swap wipes it and the next run self-heals (re-validates poster existence).
"""
import json
import os
import subprocess
import urllib.parse
import urllib.request

import store

_HTTP_TIMEOUT = 8
_GENRE_MAX_AGE_S = 30 * 86400

# Conservative kid-safe heuristic: must carry a clearly-kids genre and none that rule it
# out. kidSafe should really be override-driven (the parent knows) — this only seeds a
# sensible default; a wrong guess is corrected in studio-overrides.json, and unknown ⇒ False
# ⇒ omitted (never a guess-true badge). See risks in the plan.
_KID_GENRES = {"Animation", "Family"}
_ADULT_GENRES = {"Horror", "War", "Crime", "Thriller"}


# --- pure helpers (unit-tested) ---------------------------------------------

def pick_best_match(results, want_year, tol=1):
    """First TMDB search result whose release year is within ±tol of want_year (results
    are relevance-ranked, not exact, so the year disambiguates reissues). Returns
    (result, confidence) — 'exact' | 'loose' — or (None, None) when nothing fits."""
    try:
        wy = int(want_year)
    except (TypeError, ValueError):
        wy = None
    for r in results or []:
        rd = (r.get("release_date") or "")[:4]
        if not rd.isdigit():
            continue
        ry = int(rd)
        if wy is None:
            return r, "loose"
        if ry == wy:
            return r, "exact"
        if abs(ry - wy) <= tol:
            return r, "loose"
    return None, None


def genre_names(genre_ids, genre_map):
    """Map TMDB genre ids -> names, skipping unknown. genre_map keys arrive as strings
    from JSON while ids are ints, so try both."""
    out = []
    for gid in genre_ids or []:
        name = genre_map.get(str(gid)) or genre_map.get(gid)
        if name:
            out.append(name)
    return out


def poster_url(poster_path, image_base, size):
    """Full TMDB image URL, or None when there's no poster_path."""
    if not poster_path:
        return None
    return image_base.rstrip("/") + "/" + size + poster_path


def served_poster_url(movie_id):
    """Root-relative URL the Roku fetches — resolves to STUDIO_ROOT/.art/<id>.jpg via the
    app.py `.art` dispatch (the Roku prepends its SALLY_API_BASE)."""
    return "/media/.art/" + movie_id + ".jpg"


def kid_safe_from_genres(genres):
    gs = set(genres or [])
    return bool(gs & _KID_GENRES) and not (gs & _ADULT_GENRES)


def valid_jpeg(data):
    """SOI marker check — same gate app.py:_sniff_ok uses, so a truncated/HTML error body
    is rejected before it lands on disk."""
    return bool(data) and data[:3] == b"\xff\xd8\xff"


# --- thin I/O (injectable; mocked in tests) ---------------------------------

class TmdbClient:
    """v3 api_key query-param auth over urllib. Every call returns None on any failure
    (offline/timeout/429/JSON error), so callers frame-grab instead of crashing."""

    def __init__(self, api_key, api_base="https://api.themoviedb.org/3", timeout=_HTTP_TIMEOUT):
        self._key = api_key
        self._base = api_base.rstrip("/")
        self._timeout = timeout

    def _get(self, path, params):
        p = dict(params or {})
        p["api_key"] = self._key
        url = self._base + path + "?" + urllib.parse.urlencode(p)
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as resp:
                return json.load(resp)
        except Exception:
            return None

    def search_movie(self, title, year):
        data = self._get("/search/movie", {"query": title, "year": year})
        return None if data is None else (data.get("results") or [])

    def movie(self, tmdb_id):
        return self._get("/movie/%s" % tmdb_id, {})

    def genre_list(self):
        data = self._get("/genre/movie/list", {})
        if not data:
            return None
        return {str(g["id"]): g["name"] for g in (data.get("genres") or []) if g.get("id") is not None}


def download_poster(image_base, size, poster_path, dest, opener=None):
    """GET the poster, validate JPEG magic, atomic-replace into dest. False on any error."""
    url = poster_url(poster_path, image_base, size)
    if not url:
        return False
    try:
        opn = opener.open if opener is not None else urllib.request.urlopen
        with opn(url, timeout=_HTTP_TIMEOUT) as resp:
            data = resp.read()
    except Exception:
        return False
    if not valid_jpeg(data):
        return False
    try:
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        tmp = dest + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
    except OSError:
        return False
    return True


def frame_grab(video_path, dest, ffmpeg=None):
    """Offline/unmatched fallback poster — one frame via ffmpeg, the exact recipe
    media-encode-video.sh uses for trip-video thumbnails. False on any error."""
    ffmpeg = ffmpeg or os.environ.get("MEDIA_FFMPEG", "ffmpeg")
    try:
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        subprocess.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", video_path,
             "-vf", "thumbnail,scale=480:270:force_original_aspect_ratio=increase,crop=480:270",
             "-frames:v", "1", "-q:v", "3", "-f", "image2", dest],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        return os.path.isfile(dest)
    except Exception:
        return False


# --- orchestration ----------------------------------------------------------

def _genres_stale(index, now):
    return (now - (index.get("genresFetchedAt") or 0)) > _GENRE_MAX_AGE_S


def _persist(index, index_path):
    try:
        store.atomic_write_json(index_path, index)
    except OSError:
        pass


def _refresh_one(m, dest, genre_map, image_base, poster_size, client, downloader,
                 grabber, studio_root, overrides, now):
    ov = ((overrides or {}).get("movies") or {}).get(m["id"]) or {}
    title = ov.get("title") or m.get("title")
    year = ov.get("year") or m.get("year")
    tmdb_id = ov.get("tmdbId")

    match, confidence = None, None
    if client is not None:
        if tmdb_id:
            match = client.movie(tmdb_id)
            confidence = "override" if match else None
        else:
            results = client.search_movie(title, year)
            if results:
                match, confidence = pick_best_match(results, year)

    poster_path, genre_ids = None, []
    if match:
        poster_path = match.get("poster_path")
        if match.get("genre_ids") is not None:
            genre_ids = match.get("genre_ids") or []
        elif match.get("genres"):                       # /movie/<id> shape: [{id,name}]
            genre_ids = [g.get("id") for g in match["genres"] if g.get("id") is not None]
    genres = genre_names(genre_ids, genre_map)

    poster_source = None
    if poster_path and downloader(image_base, poster_size, poster_path, dest):
        poster_source = "tmdb"
    elif grabber(os.path.join(studio_root, m["relpath"]), dest):
        poster_source = "framegrab"
    served = served_poster_url(m["id"]) if poster_source else None

    kid = bool(ov["kidSafe"]) if "kidSafe" in ov else kid_safe_from_genres(genres)

    return {
        "tmdbId": (match.get("id") if match else tmdb_id),
        "matched": bool(match),
        "confidence": confidence,
        "genreIds": genre_ids,
        "genres": genres,
        "posterPath": poster_path,
        "poster": served,
        "posterSource": poster_source,
        "kidSafe": kid,
        "fetchedAt": now,
    }


def refresh_art(movies, *, studio_root, art_dir, index_path, image_base, poster_size,
                client=None, downloader=None, grabber=None, overrides=None,
                now=None, force_ids=None):
    """Incrementally enrich `movies` with TMDB metadata + posters. Returns the art index
    dict {schemaVersion, genresMovie, genresFetchedAt, movies:{id: record}}; pass
    index["movies"] to studio_index.build_movie_categories as `art`. Never raises for a
    single-movie failure — it frame-grabs and moves on."""
    downloader = downloader if downloader is not None else download_poster
    grabber = grabber if grabber is not None else frame_grab
    now = now if now is not None else store.now_s()
    force = set(force_ids or [])

    index = store.read_json(index_path, None) or {"schemaVersion": 1, "movies": {}}
    index.setdefault("movies", {})
    recs = index["movies"]

    genre_map = index.get("genresMovie") or {}
    if client is not None and (not genre_map or _genres_stale(index, now)):
        gm = client.genre_list()
        if gm:
            genre_map = gm
            index["genresMovie"] = gm
            index["genresFetchedAt"] = now

    try:
        os.makedirs(art_dir, exist_ok=True)
    except OSError:
        pass

    for m in movies:
        mid = m["id"]
        dest = os.path.join(art_dir, mid + ".jpg")
        if mid in recs and mid not in force and os.path.isfile(dest):
            continue    # already enriched with a poster on disk — no TMDB call
        recs[mid] = _refresh_one(m, dest, genre_map, image_base, poster_size, client,
                                 downloader, grabber, studio_root, overrides, now)
        _persist(index, index_path)    # incremental — survive a mid-run crash

    _persist(index, index_path)
    return index
