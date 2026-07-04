"""Unit tests for studio_art.py — TMDB match/genre/poster enrichment for the studio
library. Pure helpers are tested directly; the incremental refresh_art orchestrator is
tested with injected fakes (no network, no ffmpeg), the same "pure core + thin I/O"
split as studio_index.py.

    python3 -m unittest test_studio_art -v
"""
import os
import tempfile
import unittest

import store
import studio_art


class PureHelperTests(unittest.TestCase):
    def test_pick_best_match_exact_year(self):
        match, conf = studio_art.pick_best_match([{"id": 1, "release_date": "2006-06-09"}], "2006")
        self.assertEqual(match["id"], 1)
        self.assertEqual(conf, "exact")

    def test_pick_best_match_within_one_year_is_loose(self):
        match, conf = studio_art.pick_best_match([{"id": 1, "release_date": "2007-01-01"}], "2006")
        self.assertEqual(conf, "loose")

    def test_pick_best_match_rejects_far_year(self):
        match, conf = studio_art.pick_best_match([{"id": 1, "release_date": "2010-01-01"}], "2006")
        self.assertIsNone(match)
        self.assertIsNone(conf)

    def test_pick_best_match_takes_first_acceptable_by_year(self):
        # TMDB ranks by relevance; the year is what disambiguates a re-title/reissue.
        results = [{"id": 9, "release_date": "2010-01-01"}, {"id": 1, "release_date": "2006-01-01"}]
        match, _ = studio_art.pick_best_match(results, "2006")
        self.assertEqual(match["id"], 1)

    def test_pick_best_match_empty(self):
        self.assertEqual(studio_art.pick_best_match([], "2006"), (None, None))

    def test_genre_names_maps_known_ids_skips_unknown(self):
        # genre_map keys arrive as strings from JSON; ids are ints.
        gm = {"16": "Animation", "35": "Comedy"}
        self.assertEqual(studio_art.genre_names([16, 35, 999], gm), ["Animation", "Comedy"])

    def test_poster_url_builds_from_base_size_path(self):
        self.assertEqual(studio_art.poster_url("/p.jpg", "https://image.tmdb.org/t/p", "w342"),
                         "https://image.tmdb.org/t/p/w342/p.jpg")

    def test_poster_url_none_path_returns_none(self):
        self.assertIsNone(studio_art.poster_url(None, "https://x", "w342"))

    def test_served_poster_url_is_root_relative_art_path(self):
        self.assertEqual(studio_art.served_poster_url("cars-2006"), "/media/.art/cars-2006.jpg")

    def test_kid_safe_true_for_family_animation(self):
        self.assertTrue(studio_art.kid_safe_from_genres(["Animation", "Family"]))

    def test_kid_safe_false_when_adult_genre_present(self):
        self.assertFalse(studio_art.kid_safe_from_genres(["Animation", "Horror"]))

    def test_kid_safe_false_for_non_kids_genres(self):
        self.assertFalse(studio_art.kid_safe_from_genres(["Drama"]))

    def test_valid_jpeg_checks_magic_bytes(self):
        self.assertTrue(studio_art.valid_jpeg(b"\xff\xd8\xff\xe0rest"))
        self.assertFalse(studio_art.valid_jpeg(b"not a jpeg"))
        self.assertFalse(studio_art.valid_jpeg(b""))


class FakeClient:
    """Stand-in for TmdbClient — records calls, returns canned data, no network."""
    def __init__(self, results_by_title=None, movies_by_id=None, genre_map=None):
        self.results_by_title = results_by_title or {}
        self.movies_by_id = movies_by_id or {}
        self.genre_map = genre_map or {}
        self.searches = []
        self.genre_calls = 0

    def genre_list(self):
        self.genre_calls += 1
        return self.genre_map

    def search_movie(self, title, year):
        self.searches.append((title, year))
        return self.results_by_title.get(title)

    def movie(self, tmdb_id):
        return self.movies_by_id.get(tmdb_id)


def _fake_downloader(image_base, size, poster_path, dest):
    with open(dest, "wb") as f:
        f.write(b"\xff\xd8\xfftmdb-poster")
    return True


def _fake_grabber(video_path, dest):
    with open(dest, "wb") as f:
        f.write(b"\xff\xd8\xffframe-grab")
    return True


class RefreshArtTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.art_dir = os.path.join(self.tmp, ".art")
        self.index_path = os.path.join(self.art_dir, "index.json")
        self.movie = {"id": "cars-2006", "title": "Cars", "year": "2006",
                      "relpath": "movies/Cars (2006)/Cars (2006).mp4"}

    def _refresh(self, movies, client=None, force_ids=None, overrides=None):
        return studio_art.refresh_art(
            movies, studio_root=self.tmp, art_dir=self.art_dir, index_path=self.index_path,
            image_base="https://image.tmdb.org/t/p", poster_size="w342",
            client=client, downloader=_fake_downloader, grabber=_fake_grabber,
            now=1000, force_ids=force_ids, overrides=overrides)

    def test_match_downloads_poster_and_records_metadata(self):
        client = FakeClient(
            results_by_title={"Cars": [{"id": 920, "release_date": "2006-06-09",
                                        "poster_path": "/cars.jpg", "genre_ids": [16, 10751]}]},
            genre_map={"16": "Animation", "10751": "Family"})
        index = self._refresh([self.movie], client=client)
        rec = index["movies"]["cars-2006"]
        self.assertTrue(rec["matched"])
        self.assertEqual(rec["genres"], ["Animation", "Family"])
        self.assertEqual(rec["poster"], "/media/.art/cars-2006.jpg")
        self.assertEqual(rec["posterSource"], "tmdb")
        self.assertTrue(rec["kidSafe"])
        self.assertTrue(os.path.isfile(os.path.join(self.art_dir, "cars-2006.jpg")))

    def test_offline_no_client_falls_back_to_framegrab(self):
        index = self._refresh([self.movie], client=None)
        rec = index["movies"]["cars-2006"]
        self.assertFalse(rec["matched"])
        self.assertEqual(rec["posterSource"], "framegrab")
        self.assertEqual(rec["poster"], "/media/.art/cars-2006.jpg")
        self.assertEqual(rec["genres"], [])

    def test_no_search_result_frame_grabs(self):
        client = FakeClient(results_by_title={}, genre_map={"16": "Animation"})
        rec = self._refresh([self.movie], client=client)["movies"]["cars-2006"]
        self.assertFalse(rec["matched"])
        self.assertEqual(rec["posterSource"], "framegrab")

    def test_incremental_skips_already_cached(self):
        client = FakeClient(
            results_by_title={"Cars": [{"id": 920, "release_date": "2006-06-09",
                                        "poster_path": "/cars.jpg", "genre_ids": [16]}]},
            genre_map={"16": "Animation"})
        self._refresh([self.movie], client=client)
        self.assertEqual(len(client.searches), 1)
        self._refresh([self.movie], client=client)          # second run
        self.assertEqual(len(client.searches), 1)           # not re-searched

    def test_force_refetches_a_cached_movie(self):
        client = FakeClient(
            results_by_title={"Cars": [{"id": 920, "release_date": "2006-06-09",
                                        "poster_path": "/cars.jpg", "genre_ids": [16]}]},
            genre_map={"16": "Animation"})
        self._refresh([self.movie], client=client)
        self._refresh([self.movie], client=client, force_ids=["cars-2006"])
        self.assertEqual(len(client.searches), 2)

    def test_override_tmdb_id_uses_movie_detail_not_search(self):
        client = FakeClient(
            movies_by_id={555: {"id": 555, "poster_path": "/o.jpg",
                                "genres": [{"id": 18, "name": "Drama"}]}},
            genre_map={"18": "Drama"})
        overrides = {"movies": {"cars-2006": {"tmdbId": 555}}}
        rec = self._refresh([self.movie], client=client, overrides=overrides)["movies"]["cars-2006"]
        self.assertEqual(client.searches, [])               # searched by id, not title
        self.assertEqual(rec["tmdbId"], 555)
        self.assertEqual(rec["genres"], ["Drama"])

    def test_index_is_persisted_to_disk(self):
        client = FakeClient(
            results_by_title={"Cars": [{"id": 920, "release_date": "2006-06-09",
                                        "poster_path": "/c.jpg", "genre_ids": [16]}]},
            genre_map={"16": "Animation"})
        self._refresh([self.movie], client=client)
        on_disk = store.read_json(self.index_path)
        self.assertIn("cars-2006", on_disk["movies"])
        self.assertEqual(on_disk["genresMovie"], {"16": "Animation"})

    def test_refresh_art_output_feeds_build_movie_categories(self):
        # Integration: the art index enriches build_movie_categories into genre + kids rows.
        import studio_index
        client = FakeClient(
            results_by_title={"Cars": [{"id": 920, "release_date": "2006-06-09",
                                        "poster_path": "/c.jpg", "genre_ids": [16, 10751]}]},
            genre_map={"16": "Animation", "10751": "Family"})
        index = self._refresh([dict(self.movie, mtime=1.0)], client=client)
        cat = studio_index.build_movie_categories([dict(self.movie, mtime=1.0)], art=index["movies"])
        ids = [c["id"] for c in cat["collections"]]
        self.assertIn("kids-family", ids)
        self.assertIn("genre-animation", ids)
        self.assertEqual(cat["items"]["all"][0]["poster"], "/media/.art/cars-2006.jpg")


if __name__ == "__main__":
    unittest.main()
