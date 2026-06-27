"""Unit tests for waypoints.py — the 'next waypoint' selection that drives the map's pin
emphasis + the status-strip countdown.

    python3 -m unittest test_waypoints -v
"""
import unittest

import waypoints as wp


def _w(id, lat, lon, order=None, visited=False, favourite=False):
    d = {"id": id, "lat": lat, "lon": lon, "visited": visited}
    if order is not None:
        d["order"] = order
    if favourite:
        d["favourite"] = True
    return d


class HaversineTests(unittest.TestCase):
    def test_zero_distance(self):
        self.assertAlmostEqual(wp.haversine_km(53.5, -113.5, 53.5, -113.5), 0.0, places=6)

    def test_known_distance_roughly(self):
        # Edmonton -> Calgary is ~280 km great-circle.
        d = wp.haversine_km(53.5461, -113.4938, 51.0447, -114.0719)
        self.assertTrue(270 < d < 290, d)


class SelectNextTests(unittest.TestCase):
    HERE = (53.5392, -113.4913)

    def test_empty_is_none(self):
        self.assertIsNone(wp.select_next_waypoint([], *self.HERE))

    def test_all_visited_is_none(self):
        wps = [_w("a", 53.5692, -113.4613, order=1, visited=True)]
        self.assertIsNone(wp.select_next_waypoint(wps, *self.HERE))

    def test_route_ordered_skips_visited_lowest_order(self):
        wps = [
            _w("a", 53.5692, -113.4613, order=1, visited=True),   # already passed
            _w("c", 52.0, -114.0, order=3),
            _w("b", 53.0, -113.8, order=2),                 # the next by order
        ]
        nxt, km = wp.select_next_waypoint(wps, *self.HERE)
        self.assertEqual(nxt["id"], "b")
        self.assertIsNotNone(km)

    def test_nearest_fallback_when_no_order(self):
        wps = [
            _w("far", 52.0, -114.0),
            _w("near", 53.5492, -113.5013),  # closest to HERE
        ]
        nxt, _km = wp.select_next_waypoint(wps, *self.HERE)
        self.assertEqual(nxt["id"], "near")

    def test_distance_is_straight_line_km(self):
        wps = [_w("x", 53.5492, -113.4913, order=1)]
        _nxt, km = wp.select_next_waypoint(wps, *self.HERE)
        self.assertTrue(0.0 < km < 5.0, km)

    def test_no_gps_still_picks_by_order_with_no_distance(self):
        wps = [_w("b", 53.0, -113.8, order=2), _w("a", 53.5692, -113.4613, order=1)]
        nxt, km = wp.select_next_waypoint(wps, None, None)
        self.assertEqual(nxt["id"], "a")
        self.assertIsNone(km)

    # Favourites are saved places, never route stops — excluded from "next" (and therefore from
    # waypoint-eta-refresh's arrival auto-advance, which shares this selector).
    def test_favourite_excluded_even_with_lowest_order(self):
        wps = [_w("fav", 53.5492, -113.5013, order=0, favourite=True),  # would-be first by order
               _w("b", 53.0, -113.8, order=2)]
        nxt, _km = wp.select_next_waypoint(wps, *self.HERE)
        self.assertEqual(nxt["id"], "b")

    def test_all_favourites_is_none(self):
        wps = [_w("f1", 53.5692, -113.4613, favourite=True), _w("f2", 53.0, -113.8, favourite=True)]
        self.assertIsNone(wp.select_next_waypoint(wps, *self.HERE))

    def test_favourite_not_chosen_by_nearest_fallback(self):
        wps = [_w("favnear", 53.5442, -113.4963, favourite=True),  # closest, but a favourite
               _w("stop", 52.0, -114.0)]
        nxt, _km = wp.select_next_waypoint(wps, *self.HERE)
        self.assertEqual(nxt["id"], "stop")


if __name__ == "__main__":
    unittest.main()
