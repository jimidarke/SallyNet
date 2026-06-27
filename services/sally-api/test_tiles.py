"""Unit tests for tiles.py — the pure Web-Mercator slippy-tile math.

Stdlib unittest only (no pytest dep) so it runs anywhere, including the Pi's EOL Buster:
    python3 -m unittest test_tiles -v

The math functions take no config and touch no network/disk, so they're fully testable
off the Pi. basemap() takes an injectable `fetch` so its offline behaviour is testable too.
"""
import time
import unittest

import tiles


class WorldPxTests(unittest.TestCase):
    def test_origin_is_tile_centre_at_z0(self):
        # (0,0) sits at the centre of the single 256px tile at zoom 0.
        self.assertEqual(tiles.world_px(0.0, 0.0, 0), (128.0, 128.0))

    def test_antimeridian_spans_the_world_at_z0(self):
        self.assertAlmostEqual(tiles.world_px(0.0, 180.0, 0)[0], 256.0, places=6)
        self.assertAlmostEqual(tiles.world_px(0.0, -180.0, 0)[0], 0.0, places=6)

    def test_pixels_double_each_zoom_step(self):
        lat, lon = 52.52, 13.405
        x0, y0 = tiles.world_px(lat, lon, 10)
        x1, y1 = tiles.world_px(lat, lon, 11)
        self.assertAlmostEqual(x1, 2 * x0, places=6)
        self.assertAlmostEqual(y1, 2 * y0, places=6)

    def test_east_increases_x(self):
        self.assertGreater(tiles.world_px(0.0, 10.0, 5)[0],
                           tiles.world_px(0.0, -10.0, 5)[0])

    def test_north_decreases_y(self):
        # North is up: a more-northern latitude has a smaller pixel-y.
        self.assertLess(tiles.world_px(60.0, 0.0, 5)[1],
                        tiles.world_px(0.0, 0.0, 5)[1])


class ProjectTests(unittest.TestCase):
    CENTRE = (53.5392, -113.4913)  # near Edmonton

    def test_centre_maps_to_canvas_centre(self):
        x, y = tiles.project(self.CENTRE[0], self.CENTRE[1], self.CENTRE, 14, 1920, 1080)
        self.assertAlmostEqual(x, 960.0, places=6)
        self.assertAlmostEqual(y, 540.0, places=6)

    def test_point_east_of_centre_is_right_of_centre(self):
        x, _ = tiles.project(53.5392, -113.4613, self.CENTRE, 14, 1920, 1080)  # greater lon
        self.assertGreater(x, 960.0)

    def test_point_north_of_centre_is_above_centre(self):
        _, y = tiles.project(53.5692, -113.4913, self.CENTRE, 14, 1920, 1080)  # greater lat
        self.assertLess(y, 540.0)

    def test_project_is_world_px_minus_top_left(self):
        z, w, h = 14, 1920, 1080
        cx, cy = tiles.world_px(self.CENTRE[0], self.CENTRE[1], z)
        px, py = tiles.world_px(53.5692, -113.4613, z)
        x, y = tiles.project(53.5692, -113.4613, self.CENTRE, z, w, h)
        self.assertAlmostEqual(x, w / 2.0 + (px - cx), places=6)
        self.assertAlmostEqual(y, h / 2.0 + (py - cy), places=6)


class ViewportTests(unittest.TestCase):
    CENTRE = (53.5392, -113.4913)

    def test_tiles_cover_the_canvas(self):
        z, w, h = 14, 1920, 1080
        tl = tiles.tiles_for_viewport(self.CENTRE, z, w, h)
        for cxp, cyp in [(1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2), (w // 2, h // 2)]:
            covered = any(sx <= cxp < sx + 256 and sy <= cyp < sy + 256
                          for (_x, _y, sx, sy) in tl)
            self.assertTrue(covered, "canvas pixel %r is not covered by any tile" % ((cxp, cyp),))

    def test_tile_count_reasonable_at_1080p(self):
        tl = tiles.tiles_for_viewport(self.CENTRE, 14, 1920, 1080)
        self.assertGreaterEqual(len(tl), 35)
        self.assertLessEqual(len(tl), 54)

    def test_columns_are_one_tile_apart(self):
        tl = tiles.tiles_for_viewport(self.CENTRE, 14, 1920, 1080)
        xs = sorted(set(sx for (_x, _y, sx, _sy) in tl))
        for a, b in zip(xs, xs[1:]):
            self.assertEqual(b - a, 256)

    def test_tile_indices_wrap_x_and_are_in_range(self):
        # x indices are always within [0, 2^z); y may exceed range (caller gap-fills).
        z = 14
        n = 2 ** z
        tl = tiles.tiles_for_viewport(self.CENTRE, z, 1920, 1080)
        for (x, _y, _sx, _sy) in tl:
            self.assertTrue(0 <= x < n)


class ZoomBandTests(unittest.TestCase):
    def test_parked_and_camp_speed_is_tight(self):
        self.assertEqual(tiles.speed_to_zoom(0.0), 15)
        self.assertEqual(tiles.speed_to_zoom(8.0), 15)

    def test_speed_bands(self):
        self.assertEqual(tiles.speed_to_zoom(20.0), 14)
        self.assertEqual(tiles.speed_to_zoom(40.0), 13)
        self.assertEqual(tiles.speed_to_zoom(60.0), 12)
        self.assertEqual(tiles.speed_to_zoom(85.0), 11)
        self.assertEqual(tiles.speed_to_zoom(120.0), 10)

    def test_no_fix_defaults_to_tight(self):
        self.assertEqual(tiles.speed_to_zoom(None, has_fix=False), 15)

    def test_zoom_is_always_clamped_to_band_range(self):
        for s in [-5.0, 0.0, 5.0, 33.0, 999.0]:
            self.assertTrue(10 <= tiles.speed_to_zoom(s) <= 15)


class BasemapOfflineTests(unittest.TestCase):
    def test_basemap_is_canvas_sized_and_flags_gaps_when_offline(self):
        # Every tile fetch fails (dead uplink, cold cache): still returns a full canvas
        # image of the requested size, and reports every tile as missing.
        img, stats = tiles.basemap((53.5392, -113.4913), 14, 640, 480, fetch=lambda z, x, y: None)
        self.assertEqual(img.size, (640, 480))
        self.assertGreater(stats["missing"], 0)
        self.assertEqual(stats["fetched"], 0)


class LowZoomFillTests(unittest.TestCase):
    def _with_cache(self, fn):
        import tempfile
        old = tiles.cfg.TILE_CACHE_DIR
        tiles.cfg.TILE_CACHE_DIR = tempfile.mkdtemp()
        try:
            return fn(tiles.cfg.TILE_CACHE_DIR)
        finally:
            tiles.cfg.TILE_CACHE_DIR = old

    def test_fills_a_missing_tile_from_a_cached_lower_zoom_ancestor(self):
        import os
        from PIL import Image

        def body(d):
            pz, px, py = 12, 10, 20
            os.makedirs(os.path.join(d, str(pz), str(px)), exist_ok=True)
            Image.new("RGB", (256, 256), (10, 20, 30)).save(
                os.path.join(d, str(pz), str(px), "%d.png" % py))
            # a z14 child inside that z12 parent (x = 10<<2 + a, y = 20<<2 + b)
            child = tiles._lowzoom_fill(14, (10 << 2) + 1, (20 << 2) + 2)
            self.assertIsNotNone(child)
            self.assertEqual(child.size, (256, 256))
        self._with_cache(body)

    def test_no_ancestor_returns_none(self):
        self._with_cache(lambda d: self.assertIsNone(tiles._lowzoom_fill(14, 5, 5)))


class ThrottleTests(unittest.TestCase):
    """Negative cache + global circuit breaker — pure, time-injected (now/net) like
    mapgen._reuse_cached. These keep a tarpitting provider from being re-hammered and turn a
    cold-area stall into a fast gap-filled frame with a 'throttled' badge."""

    def setUp(self):
        import tempfile
        tiles.reset_throttle_state()
        self._old_dir = tiles.cfg.TILE_CACHE_DIR
        tiles.cfg.TILE_CACHE_DIR = tempfile.mkdtemp()  # empty -> every cache read misses

    def tearDown(self):
        tiles.cfg.TILE_CACHE_DIR = self._old_dir
        tiles.reset_throttle_state()

    @staticmethod
    def _failing_net(calls):
        def net(z, x, y):
            calls.append((z, x, y))
            return None
        return net

    def test_negative_cache_skips_network_while_a_tile_is_cooled(self):
        calls = []
        net = self._failing_net(calls)
        t = 1000.0
        self.assertIsNone(tiles.fetch_tile(14, 1, 1, _net=net, _now=t))
        self.assertEqual(len(calls), 1)
        # within the per-tile cooldown -> no second network hit for the SAME tile
        self.assertIsNone(tiles.fetch_tile(14, 1, 1, _net=net, _now=t + 1))
        self.assertEqual(len(calls), 1)
        # once the cooldown elapses, the tile is retried
        self.assertIsNone(tiles.fetch_tile(14, 1, 1, _net=net,
                                           _now=t + tiles.cfg.TILE_FAIL_COOLDOWN_S + 1))
        self.assertEqual(len(calls), 2)

    def test_breaker_trips_after_threshold_and_short_circuits(self):
        calls = []
        net = self._failing_net(calls)
        t = 2000.0
        n = tiles.cfg.TILE_BREAKER_FAILS
        for i in range(n):
            tiles.fetch_tile(14, 100 + i, 0, _net=net, _now=t)  # distinct tiles
        self.assertEqual(len(calls), n)
        self.assertTrue(tiles.is_throttled(t))
        # a FRESH tile (not negatively cached) still short-circuits on the open breaker
        tiles.fetch_tile(14, 999, 0, _net=net, _now=t)
        self.assertEqual(len(calls), n)

    def test_breaker_reopens_and_probes_after_cooldown(self):
        t = 3000.0
        for i in range(tiles.cfg.TILE_BREAKER_FAILS):
            tiles.fetch_tile(14, 200 + i, 0, _net=lambda z, x, y: None, _now=t)
        self.assertTrue(tiles.is_throttled(t))
        t2 = t + tiles.cfg.TILE_BREAKER_COOLDOWN_S + 1
        self.assertFalse(tiles.is_throttled(t2))
        probed = []

        def net_ok(z, x, y):
            probed.append(1)
            return b"PNGDATA"

        self.assertEqual(tiles.fetch_tile(14, 777, 0, _net=net_ok, _now=t2), b"PNGDATA")
        self.assertEqual(len(probed), 1)        # the breaker allowed one probe
        self.assertFalse(tiles.is_throttled(t2))  # a success re-closes it

    def test_429_throttle_lasts_until_retry_after(self):
        t = 4000.0
        tiles.note_throttle(t, retry_after=30)
        self.assertTrue(tiles.is_throttled(t))
        self.assertTrue(tiles.is_throttled(t + 29))
        self.assertFalse(tiles.is_throttled(t + 31))

    def test_basemap_reports_the_throttled_stat(self):
        offline = lambda z, x, y: None
        _img, stats = tiles.basemap((53.5392, -113.4913), 14, 320, 240, fetch=offline)
        self.assertIn("throttled", stats)
        self.assertFalse(stats["throttled"])
        tiles.note_throttle(time.time(), retry_after=60)
        _img2, stats2 = tiles.basemap((53.5392, -113.4913), 14, 320, 240, fetch=offline)
        self.assertTrue(stats2["throttled"])


if __name__ == "__main__":
    unittest.main()
