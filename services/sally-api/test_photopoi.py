"""Unit tests for media-reindex.build_photo_poi — the catalog -> photo-poi.json transform that
surfaces past-trip geotagged photos as map pins. Imported by path (the script name has a hyphen).

    python3 -m unittest test_photopoi -v
"""
import importlib.util
import os
import unittest

_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                     "scripts", "media-reindex.py"))
_spec = importlib.util.spec_from_file_location("media_reindex", _PATH)
mr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mr)


class BuildPhotoPoiTests(unittest.TestCase):
    def test_keeps_only_geotagged_photos_and_maps_fields(self):
        photos = [
            {"id": "a", "gps": {"lat": 52.66, "lon": -117.88}, "title": "Falls",
             "poster": "/t/a.jpg", "collectionId": "c1",
             "captureDatetime": "2026-07-04T15:01:10-06:00"},
            {"id": "b", "title": "No GPS", "poster": "/t/b.jpg", "collectionId": "c1"},  # dropped
        ]
        out = mr.build_photo_poi(photos)
        self.assertEqual(len(out["photos"]), 1)
        p = out["photos"][0]
        self.assertEqual((p["lat"], p["lon"]), (52.66, -117.88))
        self.assertEqual(p["thumbUrl"], "/t/a.jpg")
        self.assertEqual(p["title"], "Falls")
        self.assertEqual(p["collectionId"], "c1")
        self.assertEqual(p["capturedTs"], "2026-07-04T15:01:10-06:00")

    def test_dedupes_near_identical_coords(self):
        photos = [
            {"id": "a", "gps": {"lat": 52.6601, "lon": -117.8801}, "poster": "/t/a.jpg"},
            {"id": "b", "gps": {"lat": 52.6601, "lon": -117.8801}, "poster": "/t/b.jpg"},
        ]
        self.assertEqual(len(mr.build_photo_poi(photos)["photos"]), 1)

    def test_thumb_falls_back_to_url_without_a_poster(self):
        photos = [{"id": "a", "gps": {"lat": 1.0, "lon": 2.0}, "url": "/m/a.jpg"}]
        self.assertEqual(mr.build_photo_poi(photos)["photos"][0]["thumbUrl"], "/m/a.jpg")


if __name__ == "__main__":
    unittest.main()
