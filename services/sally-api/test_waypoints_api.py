"""Unit tests for the favourites behaviour of POST /api/waypoints: a favourite carries no route
`order` (so it's never a route stop), and `op=promote` turns one into a route stop.

    python3 -m unittest test_waypoints_api -v
"""
import os
import tempfile
import unittest

import app
import store


class WaypointFavouriteApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "waypoints.json")
        self._old_path = app.cfg.WAYPOINTS_JSON
        self._old_wp = app._waypoints
        self._old_fix = app._cached_fix
        app.cfg.WAYPOINTS_JSON = self.path
        app._waypoints = store.CachedJson(self.path, {"waypoints": []})
        app._cached_fix = lambda: {"fix": False, "lat": None, "lon": None}
        self.c = app.app.test_client()

    def tearDown(self):
        app.cfg.WAYPOINTS_JSON = self._old_path
        app._waypoints = self._old_wp
        app._cached_fix = self._old_fix

    def _list(self):
        return self.c.get("/api/waypoints").get_json()["waypoints"]

    def test_add_favourite_has_flag_no_order_and_updatedts(self):
        r = self.c.post("/api/waypoints", data={
            "op": "add", "name": "Lookout", "lat": "53.5", "lon": "-113.5",
            "favourite": "1"}).get_json()
        self.assertTrue(r["ok"])
        w = self._list()[0]
        self.assertTrue(w["favourite"])
        self.assertNotIn("order", w)        # favourites are saved places, not route stops
        self.assertIn("updatedTs", w)

    def test_add_normal_stop_has_order_and_no_favourite(self):
        self.c.post("/api/waypoints",
                    data={"op": "add", "name": "Fuel", "lat": "53.6", "lon": "-113.4"})
        w = self._list()[0]
        self.assertIn("order", w)
        self.assertNotIn("favourite", w)

    def test_promote_favourite_becomes_a_route_stop(self):
        self.c.post("/api/waypoints", data={
            "op": "add", "name": "Lookout", "lat": "53.5", "lon": "-113.5", "favourite": "1"})
        wid = self._list()[0]["id"]
        r = self.c.post("/api/waypoints", data={"op": "promote", "id": wid}).get_json()
        self.assertTrue(r["ok"])
        w = self._list()[0]
        self.assertNotIn("favourite", w)    # no longer a favourite
        self.assertIn("order", w)           # now participates in the route


if __name__ == "__main__":
    unittest.main()
