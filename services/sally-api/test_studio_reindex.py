"""Unit tests for studio_reindex.py — the thin orchestration (scan -> TMDB art -> categorize
-> write movies.json) shared by scripts/media-index-studio.py (nightly) and
scripts/media-fetch-art.py (manual). Injects fakes for the client/downloader/grabber so no
network or ffmpeg is touched.

    python3 -m unittest test_studio_reindex -v
"""
import os
import tempfile
import unittest

import sallyconf as cfg
import store
from test_studio_art import FakeClient, _fake_downloader


def _fake_grab(video_path, dest):
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with open(dest, "wb") as f:
        f.write(b"\xff\xd8\xffgrab")
    return True


class ReindexMoviesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._saved = {k: getattr(cfg, k) for k in
                       ("STUDIO_ROOT", "MOVIES_JSON", "STUDIO_ART_DIR",
                        "STUDIO_ART_INDEX", "STUDIO_OVERRIDES")}
        cfg.STUDIO_ROOT = self.tmp
        cfg.MOVIES_JSON = os.path.join(self.tmp, "movies.json")
        cfg.STUDIO_ART_DIR = os.path.join(self.tmp, ".art")
        cfg.STUDIO_ART_INDEX = os.path.join(cfg.STUDIO_ART_DIR, "index.json")
        cfg.STUDIO_OVERRIDES = os.path.join(self.tmp, "overrides.json")
        d = os.path.join(self.tmp, "movies", "Cars (2006)")
        os.makedirs(d)
        open(os.path.join(d, "Cars (2006).mp4"), "w").close()

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(cfg, k, v)

    def test_reindex_writes_movies_json_with_genre_rows_and_poster(self):
        import studio_reindex
        client = FakeClient(
            results_by_title={"Cars": [{"id": 920, "release_date": "2006-06-09",
                                        "poster_path": "/c.jpg", "genre_ids": [16]}]},
            genre_map={"16": "Animation"})
        movies, catalog = studio_reindex.reindex_movies(client=client, downloader=_fake_downloader)
        self.assertEqual(len(movies), 1)
        on_disk = store.read_json(cfg.MOVIES_JSON)
        ids = [c["id"] for c in on_disk["collections"]]
        self.assertIn("genre-animation", ids)
        self.assertIn("all", ids)
        self.assertEqual(on_disk["items"]["all"][0]["poster"], "/media/.art/cars-2006.jpg")

    def test_reindex_offline_still_writes_valid_catalog(self):
        import studio_reindex
        movies, catalog = studio_reindex.reindex_movies(client=None, grabber=_fake_grab)
        on_disk = store.read_json(cfg.MOVIES_JSON)
        self.assertIsNotNone(on_disk)
        self.assertTrue(any(c["id"] == "all" for c in on_disk["collections"]))

    def test_force_all_recomputes_ids_from_scan(self):
        import studio_reindex
        client = FakeClient(
            results_by_title={"Cars": [{"id": 920, "release_date": "2006-06-09",
                                        "poster_path": "/c.jpg", "genre_ids": [16]}]},
            genre_map={"16": "Animation"})
        studio_reindex.reindex_movies(client=client, downloader=_fake_downloader)
        self.assertEqual(len(client.searches), 1)
        studio_reindex.reindex_movies(client=client, downloader=_fake_downloader, force_all=True)
        self.assertEqual(len(client.searches), 2)   # forced re-search despite cache


class ReindexTvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._saved = {k: getattr(cfg, k) for k in
                       ("STUDIO_ROOT", "TV_JSON", "STUDIO_ART_INDEX", "STUDIO_OVERRIDES")}
        cfg.STUDIO_ROOT = self.tmp
        cfg.TV_JSON = os.path.join(self.tmp, "tv.json")
        cfg.STUDIO_ART_INDEX = os.path.join(self.tmp, ".art", "index.json")
        cfg.STUDIO_OVERRIDES = os.path.join(self.tmp, "overrides.json")
        ep = os.path.join(self.tmp, "tv", "Bluey (2018)", "Season 01", "Bluey - S01E01 - Magic.mp4")
        os.makedirs(os.path.dirname(ep))
        open(ep, "w").close()

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(cfg, k, v)

    def test_reindex_tv_writes_tv_json_with_show(self):
        import studio_reindex
        shows, model = studio_reindex.reindex_tv()
        self.assertEqual(len(shows), 1)
        on_disk = store.read_json(cfg.TV_JSON)
        self.assertIn("bluey-2018", on_disk["shows"])
        self.assertTrue(any(c["id"] == "tv-all" for c in on_disk["collections"]))


if __name__ == "__main__":
    unittest.main()
