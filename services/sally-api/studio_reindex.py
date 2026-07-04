"""Orchestrate the studio Movies re-index: scan -> TMDB art (incremental) -> categorize ->
atomic-write movies.json. Thin I/O glue around the pure studio_index + studio_art cores,
importable by scripts/media-index-studio.py (nightly timer) and scripts/media-fetch-art.py
(manual --force / --refresh). Reads paths/creds from sallyconf (env-overridable).

A network failure never fails the index — refresh_art frame-grabs per movie, and this wraps
it so a total failure falls back to whatever art is already cached, still writing a valid
movies.json (Recently Added + All Movies at minimum).
"""
import sallyconf as cfg
import store
import studio_art
import studio_index

_BUILD_CLIENT = object()   # sentinel: build the real TmdbClient from cfg (vs. an injected fake)


def _client():
    if not cfg.TMDB_API_KEY:
        return None
    return studio_art.TmdbClient(cfg.TMDB_API_KEY, api_base=cfg.TMDB_API_BASE)


def reindex_movies(force_ids=None, force_all=False, client=_BUILD_CLIENT,
                   downloader=None, grabber=None):
    """Rebuild movies.json. force_all re-fetches every scanned movie; force_ids re-fetches a
    subset. client/downloader/grabber are injectable for tests. Returns (movies, catalog)."""
    movies = studio_index.scan_movies(cfg.STUDIO_ROOT)
    if force_all:
        force_ids = [m["id"] for m in movies]
    overrides = store.read_json(cfg.STUDIO_OVERRIDES, None) or {}
    cl = _client() if client is _BUILD_CLIENT else client

    kw = {}
    if downloader is not None:
        kw["downloader"] = downloader
    if grabber is not None:
        kw["grabber"] = grabber

    try:
        index = studio_art.refresh_art(
            movies, studio_root=cfg.STUDIO_ROOT, art_dir=cfg.STUDIO_ART_DIR,
            index_path=cfg.STUDIO_ART_INDEX, image_base=cfg.TMDB_IMAGE_BASE,
            poster_size=cfg.TMDB_POSTER_SIZE, client=cl, overrides=overrides,
            force_ids=force_ids, **kw)
        art_movies = index.get("movies", {})
    except Exception as e:  # noqa: BLE001 — art must never fail the index
        print("studio reindex: art refresh failed (%s) — using cached art" % e)
        art_movies = (store.read_json(cfg.STUDIO_ART_INDEX, {}) or {}).get("movies", {})

    catalog = studio_index.build_movie_categories(movies, art=art_movies, overrides=overrides)
    store.atomic_write_json(cfg.MOVIES_JSON, catalog)
    return movies, catalog


def reindex_tv(overrides=None):
    """Rebuild tv.json: scan the tv/ tree, build the show/season/episode read-model, and
    atomic-write it. Show/episode artwork + genres come from studio-overrides.json and (when
    the art pipeline gains TV support) the .art index's shows/episodes maps — consumed here
    with no further change. Returns (shows, model)."""
    shows = studio_index.scan_tv(cfg.STUDIO_ROOT)
    if overrides is None:
        overrides = store.read_json(cfg.STUDIO_OVERRIDES, None) or {}
    art = store.read_json(cfg.STUDIO_ART_INDEX, None) or {}
    model = studio_index.build_tv_read_model(shows, art=art, overrides=overrides)
    store.atomic_write_json(cfg.TV_JSON, model)
    return shows, model
