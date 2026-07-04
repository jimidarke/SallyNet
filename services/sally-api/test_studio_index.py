"""Unit tests for studio_index.py — pure filesystem-scan + grouping logic for the
Movies/TV studio library, independently testable off the Pi (no Flask/network needed).

    python3 -m unittest test_studio_index -v
"""
import os
import tempfile
import unittest

import studio_index


def _find_col(cat, cid):
    """The collection dict with id == cid, or None."""
    return next((c for c in cat["collections"] if c["id"] == cid), None)


class ParseMovieFolderTests(unittest.TestCase):
    def test_parses_title_and_year(self):
        self.assertEqual(studio_index.parse_movie_folder("Cars (2006)"), ("Cars", "2006"))

    def test_parses_title_with_punctuation_and_extra_spacing(self):
        self.assertEqual(studio_index.parse_movie_folder("A Bug's Life  (1998)"), ("A Bug's Life", "1998"))

    def test_no_year_returns_none(self):
        self.assertIsNone(studio_index.parse_movie_folder("Cars"))

    def test_malformed_year_returns_none(self):
        self.assertIsNone(studio_index.parse_movie_folder("Cars (06)"))


class ScanMoviesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.movies_dir = os.path.join(self.tmp, "movies")
        os.makedirs(self.movies_dir)

    def _make_movie(self, folder_name, file_name=None):
        d = os.path.join(self.movies_dir, folder_name)
        os.makedirs(d)
        open(os.path.join(d, file_name or (folder_name + ".mp4")), "w").close()

    def test_finds_a_well_formed_movie(self):
        self._make_movie("Cars (2006)")
        movies = studio_index.scan_movies(self.tmp)
        self.assertEqual(len(movies), 1)
        self.assertEqual(movies[0]["title"], "Cars")
        self.assertEqual(movies[0]["year"], "2006")
        self.assertEqual(movies[0]["relpath"], "movies/Cars (2006)/Cars (2006).mp4")

    def test_id_is_stable_and_slug_based(self):
        self._make_movie("Cars (2006)")
        self.assertEqual(studio_index.scan_movies(self.tmp)[0]["id"], "cars-2006")

    def test_scan_includes_folder_mtime(self):
        # Recently Added is ordered by folder mtime, offline (no TMDB needed).
        self._make_movie("Cars (2006)")
        m = studio_index.scan_movies(self.tmp)[0]
        self.assertIn("mtime", m)
        self.assertIsInstance(m["mtime"], float)

    def test_skips_folder_with_no_video_file(self):
        os.makedirs(os.path.join(self.movies_dir, "Empty (2020)"))
        self.assertEqual(studio_index.scan_movies(self.tmp), [])

    def test_skips_folder_name_not_matching_title_year_convention(self):
        self._make_movie("RandomFolder")
        self.assertEqual(studio_index.scan_movies(self.tmp), [])

    def test_sorted_alphabetically_by_title(self):
        self._make_movie("Zorro (1990)")
        self._make_movie("Aladdin (1992)")
        titles = [m["title"] for m in studio_index.scan_movies(self.tmp)]
        self.assertEqual(titles, ["Aladdin", "Zorro"])

    def test_missing_movies_dir_returns_empty(self):
        self.assertEqual(studio_index.scan_movies(tempfile.mkdtemp()), [])


def _movie(mid, title, year, mtime=0.0):
    return {"id": mid, "title": title, "year": year,
            "relpath": "movies/%s (%s)/%s (%s).mp4" % (title, year, title, year),
            "mtime": mtime}


class BuildMovieCategoriesTests(unittest.TestCase):
    def test_all_category_holds_every_movie(self):
        cat = studio_index.build_movie_categories([_movie("cars-2006", "Cars", "2006")])
        allcat = _find_col(cat, "all")
        self.assertIsNotNone(allcat)
        self.assertEqual(allcat["kind"], "category")
        self.assertEqual(allcat["title"], "All Movies")
        self.assertEqual(allcat["itemCount"], 1)
        self.assertEqual(allcat["detailUrl"], "/api/collections/all")
        self.assertEqual(cat["items"]["all"][0]["id"], "cars-2006")

    def test_all_category_is_always_last(self):
        cat = studio_index.build_movie_categories([_movie("cars-2006", "Cars", "2006")])
        self.assertEqual(cat["collections"][-1]["id"], "all")

    def test_empty_movies_still_returns_the_all_category(self):
        cat = studio_index.build_movie_categories([])
        self.assertEqual(cat["collections"][0]["itemCount"], 0)
        self.assertEqual(cat["items"]["all"], [])

    def test_recently_added_row_ordered_by_mtime_desc(self):
        movies = [_movie("old-2001", "Old", "2001", mtime=100.0),
                  _movie("new-2002", "New", "2002", mtime=200.0)]
        cat = studio_index.build_movie_categories(movies)
        recent = _find_col(cat, "recently-added")
        self.assertIsNotNone(recent)
        self.assertEqual(recent["title"], "Recently Added")
        self.assertEqual([i["id"] for i in cat["items"]["recently-added"]], ["new-2002", "old-2001"])

    def test_poster_and_genres_from_art_attached_to_items(self):
        movies = [_movie("cars-2006", "Cars", "2006")]
        art = {"cars-2006": {"poster": "/media/.art/cars-2006.jpg",
                             "genres": ["Animation", "Family"], "kidSafe": True}}
        cat = studio_index.build_movie_categories(movies, art=art)
        item = cat["items"]["all"][0]
        self.assertEqual(item["poster"], "/media/.art/cars-2006.jpg")
        self.assertEqual(item["genres"], ["Animation", "Family"])
        self.assertTrue(item["kidSafe"])

    def test_kidsafe_emitted_only_when_true(self):
        # _prune keeps False (drops only None), so a False must be OMITTED at the source
        # or it would wrongly light the KIDS badge on the Roku.
        movies = [_movie("x-2000", "X", "2000")]
        for val in (False, None):
            cat = studio_index.build_movie_categories(movies, art={"x-2000": {"kidSafe": val}})
            self.assertNotIn("kidSafe", cat["items"]["all"][0])

    def test_kids_family_row_from_kidsafe(self):
        movies = [_movie("bluey-2018", "Bluey", "2018"), _movie("saw-2004", "Saw", "2004")]
        art = {"bluey-2018": {"kidSafe": True}}
        cat = studio_index.build_movie_categories(movies, art=art)
        kids = _find_col(cat, "kids-family")
        self.assertIsNotNone(kids)
        self.assertEqual(kids["title"], "Kids & Family")
        self.assertEqual(kids["itemCount"], 1)
        self.assertEqual(cat["items"]["kids-family"][0]["id"], "bluey-2018")

    def test_no_kids_row_when_nothing_kidsafe(self):
        cat = studio_index.build_movie_categories([_movie("saw-2004", "Saw", "2004")])
        self.assertIsNone(_find_col(cat, "kids-family"))

    def test_genre_rows_ordered_by_count_then_name(self):
        movies = [_movie("a-2000", "A", "2000"), _movie("b-2001", "B", "2001"),
                  _movie("c-2002", "C", "2002")]
        art = {"a-2000": {"genres": ["Action", "Comedy"]},
               "b-2001": {"genres": ["Action"]},
               "c-2002": {"genres": ["Drama"]}}
        cat = studio_index.build_movie_categories(movies, art=art)
        genre_cols = [c for c in cat["collections"] if c["id"].startswith("genre-")]
        # Action has 2, Comedy/Drama 1 each -> Action first, then alpha.
        self.assertEqual([c["title"] for c in genre_cols], ["Action", "Comedy", "Drama"])
        self.assertEqual(_find_col(cat, "genre-action")["itemCount"], 2)

    def test_override_beats_art(self):
        movies = [_movie("cars-2006", "Cars", "2006")]
        art = {"cars-2006": {"genres": ["Animation"], "kidSafe": False}}
        overrides = {"movies": {"cars-2006": {"genres": ["Family"], "kidSafe": True}}}
        cat = studio_index.build_movie_categories(movies, art=art, overrides=overrides)
        item = cat["items"]["all"][0]
        self.assertEqual(item["genres"], ["Family"])
        self.assertTrue(item["kidSafe"])
        self.assertIsNotNone(_find_col(cat, "kids-family"))

    def test_item_url_is_percent_encoded_for_real_playback(self):
        # Regression: an unencoded space/comma/paren in the URL breaks the Roku's HTTP
        # fetch entirely (confirmed live: curl on the raw path returns no response at
        # all, vs 206 once encoded) — movie filenames are human-style, unlike Trips'
        # pipeline-generated ASCII-safe names, so this must be encoded at the source.
        movies = [{"id": "20-000-leagues-1954", "title": "20,000 Leagues Under the Sea",
                   "year": "1954",
                   "relpath": "movies/20,000 Leagues Under the Sea (1954)/"
                              "20,000 Leagues Under the Sea (1954).mp4"}]
        cat = studio_index.build_movie_categories(movies)
        url = cat["items"]["all"][0]["url"]
        self.assertNotIn(" ", url)
        self.assertEqual(url, "/media/movies/20%2C000%20Leagues%20Under%20the%20Sea%20%281954%29/"
                              "20%2C000%20Leagues%20Under%20the%20Sea%20%281954%29.mp4")

    def test_item_url_still_starts_with_media_prefix_for_simple_names(self):
        movies = [_movie("cars-2006", "Cars", "2006")]
        cat = studio_index.build_movie_categories(movies)
        self.assertEqual(cat["items"]["all"][0]["url"],
                          "/media/movies/Cars%20%282006%29/Cars%20%282006%29.mp4")


if __name__ == "__main__":
    unittest.main()
