"""Unit tests for trail.py — reading today's GPX breadcrumb for the map's trail layer.

    python3 -m unittest test_trail -v
"""
import os
import tempfile
import unittest

import trail


class TodayPathTests(unittest.TestCase):
    def test_uses_utc_date_filename(self):
        # Epoch 0 = 1970-01-01 00:00:00 UTC (unambiguous) -> 1970-01-01.gpx in the tracks dir.
        p = trail.today_gpx_path("/var/lib/sally/tracks", now=0)
        self.assertEqual(p, "/var/lib/sally/tracks/1970-01-01.gpx")


class IterPointsTests(unittest.TestCase):
    SAMPLE = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="sally-track-logger" '
        'xmlns="http://www.topografix.com/GPX/1/1">\n'
        ' <trk><name>Sally 2026-06-27</name>\n  <trkseg>\n'
        '   <trkpt lat="53.5461044" lon="-113.4938189"><ele>669.2</ele>'
        '<time>2026-06-27T06:55:18Z</time></trkpt>\n'
        '   <trkpt lat="53.5492000" lon="-113.4913000"><ele>670.0</ele>'
        '<time>2026-06-27T07:00:32Z</time></trkpt>\n'
        '  </trkseg>\n </trk>\n</gpx>\n'
    )

    def test_parses_points_in_order(self):
        with tempfile.NamedTemporaryFile("w", suffix=".gpx", delete=False) as f:
            f.write(self.SAMPLE)
            path = f.name
        try:
            pts = trail._iter_gpx_points(path)
        finally:
            os.unlink(path)
        self.assertEqual(pts, [(53.5461044, -113.4938189), (53.5492, -113.4913)])

    def test_missing_file_is_empty(self):
        self.assertEqual(trail._iter_gpx_points("/no/such/track.gpx"), [])


class DownsampleTests(unittest.TestCase):
    def test_short_trail_unchanged(self):
        pts = [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]
        self.assertEqual(trail._downsample(pts, 100), pts)

    def test_long_trail_capped_keeping_endpoints(self):
        pts = [(float(i), float(i)) for i in range(1000)]
        out = trail._downsample(pts, 100)
        self.assertLessEqual(len(out), 101)
        self.assertEqual(out[0], pts[0])
        self.assertEqual(out[-1], pts[-1])  # Sally's most recent position is never dropped


class TrailCacheTests(unittest.TestCase):
    def test_returns_points_for_todays_file(self):
        d = tempfile.mkdtemp()
        # write a file for a known "now"
        now = 1782629718  # 2026-06-27
        path = trail.today_gpx_path(d, now=now)
        with open(path, "w") as f:
            f.write(IterPointsTests.SAMPLE)
        c = trail.TrailCache(d)
        pts = c.get(now=now)
        self.assertEqual(len(pts), 2)

    def test_no_file_today_returns_empty(self):
        d = tempfile.mkdtemp()
        c = trail.TrailCache(d)
        self.assertEqual(c.get(now=1782629718), [])


if __name__ == "__main__":
    unittest.main()
