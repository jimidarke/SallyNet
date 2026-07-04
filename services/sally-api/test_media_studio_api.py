"""Unit tests for the Movies studio-library additions to /api/media, /api/collections/<id>,
and /media/<path> — the first test coverage this route family has had.

    python3 -m unittest test_media_studio_api -v
"""
import os
import tempfile
import unittest

import app
import store


class MoviesApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.studio_root = os.path.join(self.tmp, "studio")
        movie_dir = os.path.join(self.studio_root, "movies", "Cars (2006)")
        os.makedirs(movie_dir)
        with open(os.path.join(movie_dir, "Cars (2006).mp4"), "wb") as f:
            f.write(b"0123456789")  # 10 bytes, enough for a Range test

        self.movies_json = os.path.join(self.tmp, "movies.json")
        self._old_studio_root = app.cfg.STUDIO_ROOT
        self._old_movies_json = app.cfg.MOVIES_JSON
        self._old_movies = app._movies
        self._old_fix = app._cached_fix
        app.cfg.STUDIO_ROOT = self.studio_root
        app.cfg.MOVIES_JSON = self.movies_json
        app._movies = store.CachedJson(self.movies_json, {"collections": [], "items": {}})
        app._cached_fix = lambda: {"fix": False, "lat": None, "lon": None}
        self.c = app.app.test_client()

    def tearDown(self):
        app.cfg.STUDIO_ROOT = self._old_studio_root
        app.cfg.MOVIES_JSON = self._old_movies_json
        app._movies = self._old_movies
        app._cached_fix = self._old_fix

    def _seed_catalog(self):
        store.atomic_write_json(self.movies_json, {
            "collections": [{"id": "all", "kind": "category", "title": "All Movies",
                              "itemCount": 1, "detailUrl": "/api/collections/all"}],
            "items": {"all": [{"id": "cars-2006", "type": "video", "title": "Cars",
                                "url": "/media/movies/Cars (2006)/Cars (2006).mp4",
                                "year": "2006"}]},
        })
        app._movies.invalidate()

    def test_type_movies_returns_the_all_movies_collection(self):
        self._seed_catalog()
        d = self.c.get("/api/media?type=movies").get_json()
        self.assertEqual(d["type"], "movies")
        self.assertEqual(len(d["collections"]), 1)
        self.assertEqual(d["collections"][0]["title"], "All Movies")

    def test_type_movies_empty_when_nothing_indexed_yet(self):
        d = self.c.get("/api/media?type=movies").get_json()
        self.assertEqual(d["collections"], [])

    def test_type_tv_still_reserved_empty(self):
        # Regression: type=tv isn't built until Phase 3 — must not error.
        d = self.c.get("/api/media?type=tv").get_json()
        self.assertEqual(d["collections"], [])

    def test_type_trips_unaffected_by_movies_dispatch(self):
        # Regression: adding the movies branch must not change the trips response shape.
        d = self.c.get("/api/media?type=trips").get_json()
        self.assertEqual(d["type"], "trips")
        self.assertIn("collections", d)

    def test_collections_all_returns_movie_items(self):
        self._seed_catalog()
        d = self.c.get("/api/collections/all").get_json()
        self.assertEqual(d["items"][0]["id"], "cars-2006")
        self.assertEqual(d["items"][0]["title"], "Cars")

    def test_media_file_range_request_serves_movie(self):
        r = self.c.get("/media/movies/Cars%20(2006)/Cars%20(2006).mp4",
                        headers={"Range": "bytes=0-3"})
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r.data, b"0123")

    def test_media_file_traversal_probe_rejected(self):
        r = self.c.get("/media/movies/../../../../etc/passwd")
        self.assertIn(r.status_code, (403, 404))

    def test_media_file_trips_root_unaffected(self):
        # Regression: a path under the (unindexed-in-this-test) trips root should still
        # dispatch to MEDIA_ROOT, not STUDIO_ROOT — 404 here (no such file), never 403.
        r = self.c.get("/media/trips/some-trip/videos/x.mp4")
        self.assertEqual(r.status_code, 404)

    def test_media_file_serves_art_poster_from_studio_root(self):
        # TMDB posters cache to STUDIO_ROOT/.art/<id>.jpg and are served root-relative as
        # /media/.art/<id>.jpg — needs ".art" in the studio dispatch set.
        art_dir = os.path.join(self.studio_root, ".art")
        os.makedirs(art_dir)
        with open(os.path.join(art_dir, "cars-2006.jpg"), "wb") as f:
            f.write(b"\xff\xd8\xffJPEGDATA")
        r = self.c.get("/media/.art/cars-2006.jpg")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, b"\xff\xd8\xffJPEGDATA")
        self.assertEqual(r.headers["Content-Type"], "image/jpeg")

    def test_media_file_multi_chunk_range_is_byte_correct(self):
        # Regression for the chunk-size reduction (mitigates a waitress disk-buffer
        # race on client disconnect, see git history): a range spanning many chunks
        # must still stitch back together to the exact requested bytes, no gaps/dupes.
        big_dir = os.path.join(self.studio_root, "movies", "Big (2000)")
        os.makedirs(big_dir)
        payload = bytes(i % 256 for i in range(200000))
        with open(os.path.join(big_dir, "Big (2000).mp4"), "wb") as f:
            f.write(payload)
        r = self.c.get("/media/movies/Big%20(2000)/Big%20(2000).mp4",
                        headers={"Range": "bytes=100-150099"})
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r.data, payload[100:150100])


class TvApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tv_json = os.path.join(self.tmp, "tv.json")
        self._old_tv = app._tv
        self._old_fix = app._cached_fix
        app._tv = store.CachedJson(self.tv_json, {"collections": [], "items": {}, "shows": {}})
        app._cached_fix = lambda: {"fix": False, "lat": None, "lon": None}
        self.c = app.app.test_client()

    def tearDown(self):
        app._tv = self._old_tv
        app._cached_fix = self._old_fix

    def _seed(self):
        store.atomic_write_json(self.tv_json, {
            "collections": [{"id": "tv-all", "kind": "category", "title": "All Shows",
                             "itemCount": 1, "detailUrl": "/api/collections/tv-all"}],
            "items": {"tv-all": [{"id": "bluey-2018", "type": "show", "title": "Bluey",
                                  "seasonCount": 1, "episodeCount": 1,
                                  "detailUrl": "/api/show/bluey-2018"}]},
            "shows": {"bluey-2018": {"id": "bluey-2018", "kind": "show", "title": "Bluey",
                                     "seasons": [{"season": 1, "id": "bluey-2018-s01",
                                                  "title": "Season 1", "episodeCount": 1,
                                                  "episodes": [{"id": "bluey-2018-s01e01",
                                                                "type": "video", "season": 1,
                                                                "episode": 1, "title": "Magic",
                                                                "url": "/media/tv/x.mp4"}]}]}},
        })
        app._tv.invalidate()

    def test_type_tv_empty_when_unseeded(self):
        d = self.c.get("/api/media?type=tv").get_json()
        self.assertEqual(d["collections"], [])

    def test_type_tv_returns_show_rows_when_seeded(self):
        self._seed()
        d = self.c.get("/api/media?type=tv").get_json()
        self.assertEqual(d["type"], "tv")
        self.assertEqual(d["collections"][0]["id"], "tv-all")

    def test_collections_tv_all_returns_show_cards(self):
        self._seed()
        d = self.c.get("/api/collections/tv-all").get_json()
        self.assertEqual(d["items"][0]["id"], "bluey-2018")
        self.assertEqual(d["items"][0]["type"], "show")

    def test_show_detail_returns_seasons_and_episodes(self):
        self._seed()
        d = self.c.get("/api/show/bluey-2018").get_json()
        self.assertEqual(d["kind"], "show")
        self.assertEqual(d["seasons"][0]["episodes"][0]["id"], "bluey-2018-s01e01")

    def test_show_detail_unknown_is_404(self):
        self._seed()
        self.assertEqual(self.c.get("/api/show/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
