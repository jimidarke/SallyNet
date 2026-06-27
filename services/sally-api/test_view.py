"""Unit tests for the shared, persisted map view-state (/api/view) + the layer resolution that
makes every browser AND the Roku glass render the SAME layers.

    python3 -m unittest test_view -v
"""
import os
import tempfile
import unittest

import app
import mapgen
import store


class ParseLayersTests(unittest.TestCase):
    """_parse_layers(arg, default_layers): an explicit ?layers= overrides for a one-off; with no
    arg the shared default set is used (the Roku sends no layers, so it inherits shared state)."""

    def test_no_override_uses_the_shared_default(self):
        self.assertEqual(app._parse_layers(None, ["base", "trail"]), {"base", "trail"})

    def test_explicit_override_wins(self):
        self.assertEqual(app._parse_layers("poi", ["base", "trail"]), {"poi"})

    def test_unknown_override_names_filtered_then_fall_back_to_default(self):
        self.assertEqual(app._parse_layers("bogus", ["base"]), {"base"})

    def test_empty_default_with_no_arg_falls_back_to_all(self):
        self.assertEqual(app._parse_layers(None, []), set(mapgen.ALL_LAYERS))


class ViewEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "view-state.json")
        self._old_path = app.cfg.VIEW_STATE_JSON
        self._old_view = app._view
        self._old_fix = app._cached_fix
        app.cfg.VIEW_STATE_JSON = self.path
        # No `layers` in the default -> a fresh install genuinely falls back to "all layers".
        app._view = store.CachedJson(self.path, {
            "schemaVersion": app.cfg.SCHEMA_VERSION, "baseSource": "street"})
        app._cached_fix = lambda: {"fix": False, "lat": None, "lon": None,
                                   "speed_kmh": None, "heading": None}
        self.c = app.app.test_client()

    def tearDown(self):
        app.cfg.VIEW_STATE_JSON = self._old_path
        app._view = self._old_view
        app._cached_fix = self._old_fix

    def test_get_defaults_to_all_layers_when_no_file(self):
        d = self.c.get("/api/view").get_json()
        self.assertEqual(set(d["layers"]), set(mapgen.ALL_LAYERS))
        self.assertEqual(d["baseSource"], "street")
        self.assertEqual(set(d["allLayers"]), set(mapgen.ALL_LAYERS))

    def test_post_persists_a_subset(self):
        self.assertTrue(self.c.post("/api/view", data={"layers": "base,trail"}).get_json()["ok"])
        self.assertEqual(set(self.c.get("/api/view").get_json()["layers"]), {"base", "trail"})

    def test_post_drops_unknown_layer_names(self):
        self.c.post("/api/view", data={"layers": "base,bogus"})
        self.assertEqual(set(self.c.get("/api/view").get_json()["layers"]), {"base"})

    def test_post_empty_selection_rejected(self):
        self.assertEqual(self.c.post("/api/view", data={"layers": ""}).status_code, 400)

    def test_post_last_write_wins(self):
        self.c.post("/api/view", data={"layers": "base"})
        self.c.post("/api/view", data={"layers": "base,poi"})
        self.assertEqual(set(self.c.get("/api/view").get_json()["layers"]), {"base", "poi"})

    def test_map_png_no_param_renders_with_shared_state(self):
        # The Roku path: /api/map.png with NO layers param must render from the shared state.
        self.c.post("/api/view", data={"layers": "base,status"})
        r = self.c.get("/api/map.png?w=320&h=240")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "image/png")


if __name__ == "__main__":
    unittest.main()
