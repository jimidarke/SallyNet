"""Unit tests for the TV Shows logic in studio_index.py — folder/episode parsing, the
show/season/episode scan, and the tv.json read-model. Off-Pi, no Flask/network.

    python3 -m unittest test_studio_tv -v
"""
import os
import tempfile
import unittest

import studio_index


class ParseShowFolderTests(unittest.TestCase):
    def test_title_and_year(self):
        self.assertEqual(studio_index.parse_show_folder("Bluey (2018)"), ("Bluey", "2018"))

    def test_title_without_year(self):
        self.assertEqual(studio_index.parse_show_folder("The Office"), ("The Office", None))


class ParseSeasonFolderTests(unittest.TestCase):
    def test_season_number(self):
        self.assertEqual(studio_index.parse_season_folder("Season 01"), 1)
        self.assertEqual(studio_index.parse_season_folder("Season 10"), 10)

    def test_specials_is_season_zero(self):
        self.assertEqual(studio_index.parse_season_folder("Specials"), 0)
        self.assertEqual(studio_index.parse_season_folder("specials"), 0)

    def test_unrecognised_returns_none(self):
        self.assertIsNone(studio_index.parse_season_folder("Bonus"))


class ParseEpisodeTests(unittest.TestCase):
    def test_authoritative_sxxeyy_with_title(self):
        self.assertEqual(studio_index.parse_episode("Bluey - S01E03 - Daddy Robot.mp4"),
                         (1, 3, "Daddy Robot"))

    def test_sxxeyy_without_title(self):
        self.assertEqual(studio_index.parse_episode("Bluey S01E03.mp4"), (1, 3, None))

    def test_loose_dxd_fallback(self):
        self.assertEqual(studio_index.parse_episode("Bluey - 1x03 - Title.mp4"), (1, 3, "Title"))

    def test_case_insensitive(self):
        self.assertEqual(studio_index.parse_episode("show.s02e05.mp4"), (2, 5, None))

    def test_takes_first_of_multi_episode(self):
        self.assertEqual(studio_index.parse_episode("Show S01E03E04.mp4")[:2], (1, 3))

    def test_unparseable_returns_none(self):
        self.assertIsNone(studio_index.parse_episode("random clip.mp4"))


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()


class ScanTvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tv = os.path.join(self.tmp, "tv")

    def _ep(self, show, season, fname):
        _touch(os.path.join(self.tv, show, season, fname))

    def test_missing_tv_dir_returns_empty(self):
        self.assertEqual(studio_index.scan_tv(self.tmp), [])

    def test_scans_show_seasons_episodes(self):
        self._ep("Bluey (2018)", "Season 01", "Bluey - S01E01 - Magic Xylophone.mp4")
        self._ep("Bluey (2018)", "Season 01", "Bluey - S01E02 - Hospital.mp4")
        self._ep("Bluey (2018)", "Season 02", "Bluey - S02E01 - Dance Mode.mp4")
        shows = studio_index.scan_tv(self.tmp)
        self.assertEqual(len(shows), 1)
        s = shows[0]
        self.assertEqual(s["id"], "bluey-2018")
        self.assertEqual(s["title"], "Bluey")
        self.assertEqual(len(s["seasons"]), 2)
        s1 = s["seasons"][0]
        self.assertEqual(s1["season"], 1)
        self.assertEqual(s1["id"], "bluey-2018-s01")
        self.assertEqual(len(s1["episodes"]), 2)
        ep = s1["episodes"][0]
        self.assertEqual(ep["id"], "bluey-2018-s01e01")
        self.assertEqual(ep["title"], "Magic Xylophone")
        self.assertEqual(ep["relpath"], "tv/Bluey (2018)/Season 01/Bluey - S01E01 - Magic Xylophone.mp4")

    def test_only_playable_mp4_episodes_enter_the_model(self):
        # A non-re-encoded .mkv is hidden "for free" (A5 rule).
        self._ep("Bluey (2018)", "Season 01", "Bluey - S01E01 - Playable.mp4")
        self._ep("Bluey (2018)", "Season 01", "Bluey - S01E02 - Pending.mkv")
        s = studio_index.scan_tv(self.tmp)[0]
        eps = s["seasons"][0]["episodes"]
        self.assertEqual([e["episode"] for e in eps], [1])

    def test_show_with_no_playable_episodes_is_skipped(self):
        self._ep("Ghost (2020)", "Season 01", "Ghost - S01E01.mkv")   # only unplayable
        self.assertEqual(studio_index.scan_tv(self.tmp), [])

    def test_episodes_sorted_by_number(self):
        self._ep("Bluey (2018)", "Season 01", "Bluey - S01E03 - C.mp4")
        self._ep("Bluey (2018)", "Season 01", "Bluey - S01E01 - A.mp4")
        s = studio_index.scan_tv(self.tmp)[0]
        self.assertEqual([e["episode"] for e in s["seasons"][0]["episodes"]], [1, 3])


def _show_fixture():
    return [{
        "id": "bluey-2018", "title": "Bluey", "year": "2018", "relroot": "tv/Bluey (2018)",
        "mtime": 100.0,
        "seasons": [{"season": 1, "id": "bluey-2018-s01", "episodes": [
            {"id": "bluey-2018-s01e01", "season": 1, "episode": 1, "title": "Magic Xylophone",
             "relpath": "tv/Bluey (2018)/Season 01/Bluey - S01E01 - Magic Xylophone.mp4"},
        ]}],
    }]


class BuildTvReadModelTests(unittest.TestCase):
    def test_empty_shows_is_reserved_empty(self):
        m = studio_index.build_tv_read_model([])
        self.assertEqual(m["collections"], [])
        self.assertEqual(m["shows"], {})

    def test_all_shows_row_and_show_card(self):
        m = studio_index.build_tv_read_model(_show_fixture())
        ids = [c["id"] for c in m["collections"]]
        self.assertIn("tv-all", ids)
        card = m["items"]["tv-all"][0]
        self.assertEqual(card["id"], "bluey-2018")
        self.assertEqual(card["type"], "show")
        self.assertEqual(card["seasonCount"], 1)
        self.assertEqual(card["episodeCount"], 1)
        self.assertEqual(card["detailUrl"], "/api/show/bluey-2018")

    def test_show_detail_has_seasons_and_encoded_episode_urls(self):
        m = studio_index.build_tv_read_model(_show_fixture())
        d = m["shows"]["bluey-2018"]
        self.assertEqual(d["kind"], "show")
        ep = d["seasons"][0]["episodes"][0]
        self.assertEqual(ep["id"], "bluey-2018-s01e01")
        self.assertEqual(ep["type"], "video")
        self.assertNotIn(" ", ep["url"])
        self.assertTrue(ep["url"].startswith("/media/tv/Bluey%20%282018%29/"))

    def test_genre_and_kids_rows_from_art(self):
        art = {"shows": {"bluey-2018": {"genres": ["Kids", "Comedy"], "kidSafe": True,
                                        "poster": "/media/.art/bluey-2018/poster.jpg"}}}
        m = studio_index.build_tv_read_model(_show_fixture(), art=art)
        ids = [c["id"] for c in m["collections"]]
        self.assertIn("tv-kids-family", ids)
        self.assertIn("tv-genre-comedy", ids)
        self.assertEqual(m["items"]["tv-all"][0]["poster"], "/media/.art/bluey-2018/poster.jpg")
        self.assertTrue(m["items"]["tv-all"][0]["kidSafe"])

    def test_episode_override_supplies_still_and_title(self):
        overrides = {"episodes": {"bluey-2018-s01e01": {"still": "/media/.art/x.jpg",
                                                        "title": "Override Title"}}}
        m = studio_index.build_tv_read_model(_show_fixture(), overrides=overrides)
        ep = m["shows"]["bluey-2018"]["seasons"][0]["episodes"][0]
        self.assertEqual(ep["still"], "/media/.art/x.jpg")
        self.assertEqual(ep["title"], "Override Title")


if __name__ == "__main__":
    unittest.main()
