"""Unit tests for ec_weather — the Environment Canada citypage parse + nearest-site lookup that
feed scripts/weather-refresh.py.

    python3 -m unittest test_ec_weather -v

Covers the two real-world fallbacks against a live-captured Edmonton fixture (empty current
condition/iconCode; evening period ordering where the first forecast is a night/low) and a crafted
daytime document (populated current conditions; Today-high-first ordering).
"""
import os
import unittest

import ec_weather

HERE = os.path.dirname(os.path.abspath(__file__))
SITES_CSV = os.path.join(HERE, "ec_sites.csv")
EDMONTON_XML = os.path.join(HERE, "testdata", "edmonton_sample.xml")

# Crafted daytime document: current conditions are populated (no fallback), and the first forecast is
# "Today" (a high), the second "Tonight" (a low).
DAYTIME_XML = """<?xml version="1.0" encoding="ISO-8859-1"?>
<siteData>
  <location><name code="s0000047" lat="51.05N" lon="114.07W">Calgary</name>
            <region>Calgary Region</region></location>
  <currentConditions>
    <dateTime name="observation" zone="UTC" UTCOffset="0"><hour>18</hour><minute>00</minute></dateTime>
    <dateTime name="observation" zone="MDT" UTCOffset="-6"><hour>12</hour><minute>00</minute></dateTime>
    <condition>Sunny</condition>
    <iconCode format="gif">00</iconCode>
    <temperature unitType="metric" units="C">24.6</temperature>
  </currentConditions>
  <forecastGroup>
    <forecast><period textForecastName="Today">Today</period>
      <textSummary>Sunny. High 27.</textSummary>
      <abbreviatedForecast><iconCode format="gif">00</iconCode><textSummary>Sunny</textSummary></abbreviatedForecast>
      <temperatures><temperature units="C" class="high">27</temperature></temperatures></forecast>
    <forecast><period textForecastName="Tonight">Tonight</period>
      <temperatures><temperature units="C" class="low">13</temperature></temperatures></forecast>
  </forecastGroup>
</siteData>"""

NO_TEMP_XML = """<siteData>
  <location><name code="s0000000">Nowhere</name></location>
  <currentConditions><condition>Cloudy</condition><iconCode>10</iconCode><temperature/></currentConditions>
  <forecastGroup></forecastGroup>
</siteData>"""


class NearestSiteTests(unittest.TestCase):
    def setUp(self):
        self.sites = ec_weather.load_sites(SITES_CSV)

    def test_site_list_loaded(self):
        self.assertGreater(len(self.sites), 500)

    def test_edmonton_coords_pick_edmonton(self):
        s = ec_weather.nearest_site(53.5461, -113.4938, self.sites)
        self.assertEqual(s["code"], "s0000045")
        self.assertEqual(s["prov"], "AB")

    def test_each_site_is_nearest_to_itself(self):
        # Property check on real data: querying a site's own coordinates returns that site.
        for s in (self.sites[0], self.sites[len(self.sites) // 2], self.sites[-1]):
            got = ec_weather.nearest_site(s["lat"], s["lon"], self.sites)
            self.assertEqual(got["code"], s["code"])

    def test_vancouver_coords_pick_bc(self):
        s = ec_weather.nearest_site(49.2827, -123.1207, self.sites)
        self.assertEqual(s["prov"], "BC")


class ParseEdmontonFixtureTests(unittest.TestCase):
    """Live-captured file: empty current condition/iconCode + evening ordering (first period is a low)."""
    def setUp(self):
        with open(EDMONTON_XML, encoding="utf-8") as f:
            self.w = ec_weather.parse_citypage(f.read())

    def test_current_temp_rounded(self):
        self.assertEqual(self.w["temp_c"], 20)          # 20.1 -> 20

    def test_condition_falls_back_to_forecast(self):
        self.assertEqual(self.w["condition"], "Chance of showers")

    def test_icon_falls_back_to_forecast(self):
        self.assertEqual(self.w["icon"], "39")

    def test_high_low_picked_by_class_not_position(self):
        self.assertEqual(self.w["low_c"], 12)           # "Saturday night" (first period)
        self.assertEqual(self.w["high_c"], 23)          # "Sunday" (second period)

    def test_summary_and_location_and_time(self):
        self.assertTrue(self.w["summary"].startswith("Partly cloudy"))
        self.assertEqual(self.w["location"], "Edmonton")
        self.assertEqual(self.w["observed_hm"], "16:00")  # local (MDT), not 22:00 UTC


class ParseDaytimeTests(unittest.TestCase):
    def setUp(self):
        self.w = ec_weather.parse_citypage(DAYTIME_XML)

    def test_uses_current_conditions_when_present(self):
        self.assertEqual(self.w["temp_c"], 25)          # 24.6 -> 25
        self.assertEqual(self.w["condition"], "Sunny")  # from currentConditions, not the forecast
        self.assertEqual(self.w["icon"], "00")

    def test_today_high_tonight_low(self):
        self.assertEqual(self.w["high_c"], 27)
        self.assertEqual(self.w["low_c"], 13)

    def test_local_observation_time(self):
        self.assertEqual(self.w["observed_hm"], "12:00")


class ParseDegenerateTests(unittest.TestCase):
    def test_no_temperature_returns_none(self):
        self.assertIsNone(ec_weather.parse_citypage(NO_TEMP_XML))


if __name__ == "__main__":
    unittest.main()
