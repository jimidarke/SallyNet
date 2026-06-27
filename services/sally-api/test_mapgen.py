"""Unit tests for mapgen's pure render-cache decision (the throttle that keeps the Pi from
re-rendering identical frames for every Roku poll).

    python3 -m unittest test_mapgen -v
"""
import unittest

import mapgen


class ReuseCacheTests(unittest.TestCase):
    MIN_INTERVAL = 3.0
    PARKED_TTL = 20.0
    SHAPE = (1920, 1080, "all")
    OTHER_SHAPE = (800, 480, "all")

    def reuse(self, now, last_at, last_shape, shape, last_content, content):
        return mapgen._reuse_cached(now, last_at, last_shape, shape, last_content, content,
                                    self.MIN_INTERVAL, self.PARKED_TTL)

    def test_nothing_cached_never_reuses(self):
        self.assertFalse(self.reuse(100.0, 0.0, None, self.SHAPE, None, ("c",)))

    def test_same_content_within_parked_ttl_reuses(self):
        # Parked: centre rounds to the same content -> serve the frame for up to PARKED_TTL.
        self.assertTrue(self.reuse(110.0, 100.0, self.SHAPE, self.SHAPE, ("c",), ("c",)))

    def test_same_content_beyond_parked_ttl_rerenders(self):
        # Past PARKED_TTL even a stable frame refreshes (clock / sat count tick).
        self.assertFalse(self.reuse(125.0, 100.0, self.SHAPE, self.SHAPE, ("c",), ("c",)))

    def test_changed_content_within_min_interval_reuses(self):
        # Moving: content changes every render, but the throttle floor coalesces polls.
        self.assertTrue(self.reuse(102.0, 100.0, self.SHAPE, self.SHAPE, ("a",), ("b",)))

    def test_changed_content_beyond_min_interval_rerenders(self):
        self.assertFalse(self.reuse(104.0, 100.0, self.SHAPE, self.SHAPE, ("a",), ("b",)))

    def test_different_shape_never_reuses_even_within_throttle(self):
        # A differently-sized cached frame must not satisfy this request, throttle or not.
        self.assertFalse(self.reuse(100.5, 100.0, self.OTHER_SHAPE, self.SHAPE, ("c",), ("c",)))


class CacheKeySizeTests(unittest.TestCase):
    def setUp(self):
        mapgen.reset_render_cache()

    def test_different_canvas_size_is_not_served_from_cache(self):
        # Two renders within the throttle window but at different sizes must NOT collide in
        # the render cache (a 320x240 frame must not be returned for a 640x480 request).
        import io
        from PIL import Image
        tel = {"fix": False}
        layers = set(mapgen.ALL_LAYERS)
        a = mapgen.render_map_png((53.5, -113.5), 14, 320, 240, layers, tel, {}, now=1.0)
        b = mapgen.render_map_png((53.5, -113.5), 14, 640, 480, layers, tel, {}, now=1.5)
        self.assertEqual(Image.open(io.BytesIO(a)).size, (320, 240))
        self.assertEqual(Image.open(io.BytesIO(b)).size, (640, 480))


class AlertSigTests(unittest.TestCase):
    """_alert_sig: a coarse 5 s bucket folded into the render-cache content sig so the GPS-loss
    banner + counter refresh promptly, but only when a fix has actually been missing past the
    threshold (so normal frames keep their cache behaviour)."""

    def test_with_a_fix_there_is_no_alert(self):
        self.assertIsNone(mapgen._alert_sig({"fix": True, "fix_age_s": 999}))

    def test_no_fix_age_means_no_alert(self):
        self.assertIsNone(mapgen._alert_sig({"fix": False}))

    def test_below_threshold_no_alert(self):
        self.assertIsNone(mapgen._alert_sig({"fix": False, "fix_age_s": 5}))

    def test_above_threshold_buckets_by_5s(self):
        self.assertEqual(mapgen._alert_sig({"fix": False, "fix_age_s": 40}), 8)


class GpsAlertRenderTests(unittest.TestCase):
    def setUp(self):
        mapgen.reset_render_cache()  # the module-global frame cache must not leak across tests

    def test_banner_busts_cache_and_renders(self):
        import io
        from PIL import Image
        layers = set(mapgen.ALL_LAYERS)
        calm = {"fix": False, "fix_age_s": 2}          # below threshold -> no banner
        lost = {"fix": False, "fix_age_s": 40, "had_fix": True}
        a = mapgen.render_map_png((53.5, -113.5), 14, 320, 240, layers, calm, {}, now=1000.0)
        b = mapgen.render_map_png((53.5, -113.5), 14, 320, 240, layers, lost, {}, now=1005.0)
        self.assertNotEqual(a, b)   # the alert state changed the content sig -> a fresh frame
        self.assertEqual(Image.open(io.BytesIO(b)).size, (320, 240))

    def test_render_survives_every_fix_state(self):
        layers = set(mapgen.ALL_LAYERS)
        for tel in ({"fix": True, "heading": 90, "fix_age_s": 0},
                    {"fix": False, "fix_age_s": 40, "had_fix": True},
                    {"fix": False, "fix_age_s": 40, "had_fix": False}):
            png = mapgen.render_map_png((53.5, -113.5), 15, 200, 200, layers, tel, {},
                                        now=tel["fix_age_s"] + 1)
            self.assertTrue(png)


class FavouriteRenderTests(unittest.TestCase):
    def setUp(self):
        mapgen.reset_render_cache()

    def test_favourite_renders_as_a_distinct_marker(self):
        import io
        from PIL import Image
        layers = set(mapgen.ALL_LAYERS)
        tel = {"fix": False}
        fav = {"waypoints": {"waypoints": [{"id": "f", "name": "Lookout", "lat": 53.5,
                                            "lon": -113.5, "favourite": True}]}}
        stop = {"waypoints": {"waypoints": [{"id": "s", "name": "Lookout", "lat": 53.5,
                                             "lon": -113.5, "type": "stop"}]}}
        # Renders spaced beyond PARKED_TTL so the frame cache doesn't mask the marker difference.
        a = mapgen.render_map_png((53.5, -113.5), 14, 320, 240, layers, tel, fav, now=2000.0)
        b = mapgen.render_map_png((53.5, -113.5), 14, 320, 240, layers, tel, stop, now=2030.0)
        self.assertEqual(Image.open(io.BytesIO(a)).size, (320, 240))
        self.assertNotEqual(a, b)   # gold star vs teardrop pin -> different pixels


class PhotoPoiRenderTests(unittest.TestCase):
    def setUp(self):
        mapgen.reset_render_cache()

    def test_photos_is_a_layer(self):
        self.assertIn("photos", mapgen.ALL_LAYERS)

    def test_near_photo_draws_but_far_photo_is_culled(self):
        import io
        from PIL import Image
        layers = set(mapgen.ALL_LAYERS)
        tel = {"fix": False}
        data = {"photoPoi": {"photos": [{"lat": 52.66, "lon": -117.88, "title": "Falls"}]}}
        empty = {"photoPoi": {"photos": []}}
        near = mapgen.render_map_png((52.66, -117.88), 13, 320, 240, layers, tel, data, now=3000.0)
        none = mapgen.render_map_png((52.66, -117.88), 13, 320, 240, layers, tel, empty, now=3030.0)
        far = mapgen.render_map_png((40.0, -75.0), 13, 320, 240, layers, tel, data, now=3060.0)
        farempty = mapgen.render_map_png((40.0, -75.0), 13, 320, 240, layers, tel, empty, now=3090.0)
        self.assertEqual(Image.open(io.BytesIO(near)).size, (320, 240))
        self.assertNotEqual(near, none)     # a camera glyph at centre changed the pixels
        self.assertEqual(far, farempty)     # > PHOTO_POI_MAX_KM -> culled -> identical to no-photo


class MapChipTests(unittest.TestCase):
    """The bottom-strip MAP chip decision (pure): throttled > gaps > approx > ok."""

    def test_throttled_takes_priority_over_gaps(self):
        self.assertEqual(mapgen._map_chip_state({"throttled": True, "missing": 3}),
                         ("throttled", mapgen.AMBER))

    def test_missing_tiles_show_gaps(self):
        self.assertEqual(mapgen._map_chip_state({"missing": 3}), ("3 gaps", mapgen.AMBER))

    def test_lowzoom_filled_shows_approx(self):
        self.assertEqual(mapgen._map_chip_state({"filled": 2}), ("approx", mapgen.AMBER))

    def test_all_tiles_present_shows_ok(self):
        self.assertEqual(mapgen._map_chip_state({}), ("ok", mapgen.GREEN))


if __name__ == "__main__":
    unittest.main()
