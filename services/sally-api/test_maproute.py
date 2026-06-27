"""Unit tests for the app.py map-route helpers that drive the GPS-loss overlay: centre/zoom
FREEZE at the last-known position on signal loss (instead of teleporting to the home anchor),
and the two-tier fix-age source.

    python3 -m unittest test_maproute -v
"""
import time
import unittest

import app


class CenterZoomFreezeTests(unittest.TestCase):
    def test_fix_centers_on_live_gps(self):
        gps = {"fix": True, "lat": 52.0, "lon": -118.0, "speed_kmh": 0.0}
        c, _z = app._map_center_zoom(gps, {}, {})
        self.assertEqual(c, (52.0, -118.0))

    def test_no_fix_freezes_at_last_known_not_home(self):
        gps = {"fix": False, "lat": None, "lon": None, "speed_kmh": None}
        c, _z = app._map_center_zoom(gps, {"lat": 52.0, "lon": -118.0}, {})
        self.assertEqual(c, (52.0, -118.0))

    def test_no_fix_no_last_known_falls_back_to_home(self):
        gps = {"fix": False, "lat": None, "lon": None, "speed_kmh": None}
        c, _z = app._map_center_zoom(gps, {}, {})
        self.assertEqual(c, (app.cfg.HOME_LAT, app.cfg.HOME_LON))

    def test_no_fix_freezes_zoom_band_from_last_known_speed(self):
        # A last-known highway speed keeps the wide band, NOT the tight no-fix default (ZOOM_MAX).
        gps = {"fix": False, "lat": None, "lon": None, "speed_kmh": None}
        _c, z = app._map_center_zoom(gps, {"lat": 52.0, "lon": -118.0, "speed_kmh": 100.0}, {})
        self.assertEqual(z, app.tiles.speed_to_zoom(100.0))
        self.assertLess(z, app.tiles.ZOOM_MAX)


class FixAgeTests(unittest.TestCase):
    def setUp(self):
        self._old_nav = app._nav
        self._old_lg = dict(app._last_good)

    def tearDown(self):
        app._nav = self._old_nav
        app._last_good.update(self._old_lg)

    def test_with_a_fix_age_is_zero(self):
        gps = {"fix": True, "lat": 52.0, "lon": -118.0, "speed_kmh": 5.0}
        age, lk, had = app._fix_age_and_last(gps)
        self.assertEqual(age, 0)
        self.assertTrue(had)
        self.assertEqual(lk["lat"], 52.0)

    def test_uses_navstate_when_fresh(self):
        class FakeNav:
            def get(self):
                return {"ts": int(time.time()), "secondsSinceFix": 120,
                        "lastKnown": {"lat": 52.0, "lon": -118.0}, "hadFix": True}
        app._nav = FakeNav()
        age, lk, had = app._fix_age_and_last({"fix": False, "lat": None, "lon": None})
        self.assertEqual(age, 120)
        self.assertTrue(had)
        self.assertEqual(lk["lat"], 52.0)

    def test_falls_back_to_in_process_tracker_when_navstate_stale(self):
        class StaleNav:
            def get(self):
                return {"ts": 1, "secondsSinceFix": 5}      # ancient -> ignored
        app._nav = StaleNav()
        app._last_good.update(ts=time.time() - 90, lat=52.0, lon=-118.0, speed_kmh=10.0)
        age, lk, had = app._fix_age_and_last({"fix": False, "lat": None, "lon": None})
        self.assertGreaterEqual(age, 89)
        self.assertTrue(had)
        self.assertEqual(lk["lat"], 52.0)


if __name__ == "__main__":
    unittest.main()
