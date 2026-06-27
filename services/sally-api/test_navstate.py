"""Unit tests for navstate.py — the pure nav-tick logic (fix-age + last-known + SD write-gate),
shared by scripts/nav-tick.py and tested off the Pi.

    python3 -m unittest test_navstate -v
"""
import unittest

import navstate

FIX = {"fix": True, "lat": 53.5, "lon": -113.5, "speed_kmh": 50.0, "heading": 90.0, "alt_m": 700.0}
NOFIX = {"fix": False, "lat": None, "lon": None}


class ComputeNavTests(unittest.TestCase):
    def test_fixed_sets_lastknown_and_zero_age(self):
        s = navstate.compute_nav({}, FIX, now=100, first_ts=0)
        self.assertTrue(s["fix"])
        self.assertTrue(s["hadFix"])
        self.assertEqual(s["lastFixTs"], 100)
        self.assertEqual(s["secondsSinceFix"], 0)
        self.assertEqual(s["lastKnown"]["lat"], 53.5)
        self.assertEqual(s["lastKnown"]["speed_kmh"], 50.0)

    def test_lost_after_a_fix_counts_from_last_fix_and_freezes_lastknown(self):
        prev = navstate.compute_nav({}, FIX, now=80, first_ts=0)
        s = navstate.compute_nav(prev, NOFIX, now=200, first_ts=0)
        self.assertFalse(s["fix"])
        self.assertTrue(s["hadFix"])               # still "had a fix this run"
        self.assertEqual(s["secondsSinceFix"], 120)
        self.assertEqual(s["lastFixTs"], 80)
        self.assertEqual(s["lastKnown"]["lat"], 53.5)   # frozen, not dropped

    def test_never_fixed_counts_from_first_ts_and_has_no_lastknown(self):
        s = navstate.compute_nav({}, NOFIX, now=50, first_ts=10)
        self.assertFalse(s["fix"])
        self.assertFalse(s["hadFix"])
        self.assertEqual(s["secondsSinceFix"], 40)
        self.assertIsNone(s["lastKnown"])


class ShouldWriteTests(unittest.TestCase):
    def _lost(self, ts, since):
        return {"ts": ts, "fix": False, "hadFix": True, "secondsSinceFix": since, "lastKnown": None}

    def _fixed(self, ts, lat, lon):
        return {"ts": ts, "fix": True, "hadFix": True, "secondsSinceFix": 0,
                "lastKnown": {"lat": lat, "lon": lon}}

    def test_fix_state_flip_always_writes(self):
        self.assertTrue(navstate.should_write(self._fixed(100, 53.5, -113.5),
                                              self._lost(101, 1), 100, move_m=50, healthy_s=30))
        self.assertTrue(navstate.should_write(self._lost(100, 60),
                                              self._fixed(101, 53.5, -113.5), 100, move_m=50, healthy_s=30))

    def test_lost_writes_only_when_the_bucket_advances(self):
        prev = self._lost(100, 12)               # bucket 12//5 == 2
        same = self._lost(103, 13)               # 13//5 == 2 -> same bucket
        advanced = self._lost(105, 16)           # 16//5 == 3 -> advanced
        self.assertFalse(navstate.should_write(prev, same, 100, move_m=50, healthy_s=30))
        self.assertTrue(navstate.should_write(prev, advanced, 100, move_m=50, healthy_s=30))

    def test_fixed_stationary_within_heartbeat_skips(self):
        prev = self._fixed(100, 53.5000, -113.5000)
        new = self._fixed(110, 53.50001, -113.50001)   # ~1.4 m drift
        self.assertFalse(navstate.should_write(prev, new, 100, move_m=50, healthy_s=30))

    def test_fixed_real_movement_writes(self):
        prev = self._fixed(100, 53.5000, -113.5000)
        new = self._fixed(110, 53.5010, -113.5000)     # ~111 m north
        self.assertTrue(navstate.should_write(prev, new, 100, move_m=50, healthy_s=30))

    def test_fixed_heartbeat_writes_after_healthy_interval(self):
        prev = self._fixed(100, 53.5, -113.5)
        new = self._fixed(140, 53.5, -113.5)           # stationary, but 40 s since last write
        self.assertTrue(navstate.should_write(prev, new, last_write_ts=100, move_m=50, healthy_s=30))


if __name__ == "__main__":
    unittest.main()
