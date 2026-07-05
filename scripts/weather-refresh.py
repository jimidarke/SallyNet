#!/usr/bin/env python3
"""weather-refresh.py — refresh the Environment Canada current-conditions cache for Sally's position.

Runs off a ~15 min systemd timer. A thin LOCALHOST client of sally-api plus one outbound LTE call to
Environment Canada's City Page Weather datamart. Each run resolves Sally's location (live GPS ->
frozen last-known -> Edmonton), finds the nearest EC site, fetches + parses that site's citypage XML,
and writes the compact result to WEATHER_JSON. /api/state folds that cache into its `weather` block,
so the 5 s Roku poll stays fast and network-free, and the card goes gracefully stale in cellular dead
zones (this script simply leaves the last good cache in place whenever EC is unreachable).

Location ladder mirrors the map's (app.py:_map_center_zoom): never teleport to Edmonton mid-trip when
a frozen last-known position exists. The parse/nearest-site logic is reused from the deployed sally-api
(ec_weather, imported via SALLY_API_DIR) so it never diverges. Dependency-free stdlib so it runs on the
Pi's EOL Buster.

Env (all overridable; the N100 migration is an endpoint/path change):
  SALLY_API_LOCAL    sally-api base         (default http://127.0.0.1:8090)
  SALLY_API_DIR      deployed app dir       (default /opt/sally/sally-api) — for the ec_weather import
  WEATHER_JSON       cache out              (default /var/lib/sally/weather.json)
  WEATHER_SITE_LIST  EC site table CSV      (default SALLY_API_DIR/ec_sites.csv)
  EC_BASE            citypage datamart root (default https://dd.weather.gc.ca/today/citypage_weather)
  WEATHER_USER_AGENT outbound UA            (default sally-api/1.0 (sallynet motorhome dashboard))
  NAV_STATE_JSON     frozen last-known pos  (default /var/lib/sally/nav-state.json)
  SALLY_HOME_LAT/LON Edmonton fallback      (default 53.5461 / -113.4938)
"""
import fcntl
import json
import os
import re
import sys
import time
import urllib.request

API_LOCAL = os.environ.get("SALLY_API_LOCAL", "http://127.0.0.1:8090").rstrip("/")
SALLY_API_DIR = os.environ.get("SALLY_API_DIR", "/opt/sally/sally-api")
WEATHER_JSON = os.environ.get("WEATHER_JSON", "/var/lib/sally/weather.json")
SITE_LIST = os.environ.get("WEATHER_SITE_LIST", os.path.join(SALLY_API_DIR, "ec_sites.csv"))
EC_BASE = os.environ.get("EC_BASE", "https://dd.weather.gc.ca/today/citypage_weather").rstrip("/")
USER_AGENT = os.environ.get("WEATHER_USER_AGENT", "sally-api/1.0 (sallynet motorhome dashboard)")
NAV_STATE_JSON = os.environ.get("NAV_STATE_JSON", "/var/lib/sally/nav-state.json")
HOME_LAT = float(os.environ.get("SALLY_HOME_LAT", "53.5461"))
HOME_LON = float(os.environ.get("SALLY_HOME_LON", "-113.4938"))

sys.path.insert(0, SALLY_API_DIR)
try:
    from ec_weather import load_sites, nearest_site, parse_citypage
except Exception as e:  # noqa: BLE001 — degrade, don't crash the timer
    print("cannot import ec_weather from %s (%s) — skip" % (SALLY_API_DIR, e))
    sys.exit(0)


def _http_get(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _get_json(url, timeout=5):
    return json.loads(_http_get(url, timeout).decode())


def _atomic_write_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lock = path + ".lock"
    with open(lock, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
        fcntl.flock(lf, fcntl.LOCK_UN)


def _resolve_location():
    """(lat, lon, source): live GPS -> frozen last-known -> Edmonton anchor. Mirrors the map ladder so
    the weather doesn't teleport home the moment a fix drops mid-trip."""
    try:
        gps = (_get_json(API_LOCAL + "/api/state").get("gps") or {})
        if gps.get("fix") and gps.get("lat") is not None:
            return gps["lat"], gps["lon"], "gps"
    except Exception as e:  # noqa: BLE001
        print("no /api/state (%s)" % e)
    try:
        with open(NAV_STATE_JSON) as f:
            lk = (json.load(f).get("lastKnown") or {})
        if lk.get("lat") is not None:
            return lk["lat"], lk["lon"], "last_known"
    except Exception:  # noqa: BLE001
        pass
    return HOME_LAT, HOME_LON, "home"


def _fetch_site_xml(prov, code):
    """Newest citypage XML for a site. The datamart is bucketed by UTC hour of emission, so list the
    current hour dir (falling back an hour or two when the top-of-hour file isn't written yet), pick the
    latest-timestamped file for the site code, and GET it. Returns the XML text, or None on any failure."""
    pat = re.compile(r"[0-9T.]+Z_MSC_CitypageWeather_%s_en\.xml" % re.escape(code))
    for off in range(0, 3):
        hh = time.strftime("%H", time.gmtime(time.time() - off * 3600))
        base = "%s/%s/%s/" % (EC_BASE, prov, hh)
        try:
            listing = _http_get(base, timeout=12).decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            print("list %s failed (%s)" % (base, e))
            continue
        files = pat.findall(listing)
        if files:
            newest = sorted(files)[-1]
            try:
                return _http_get(base + newest, timeout=12).decode("utf-8", "replace")
            except Exception as e:  # noqa: BLE001
                print("get %s failed (%s)" % (newest, e))
    return None


def main():
    try:
        sites = load_sites(SITE_LIST)
    except Exception as e:  # noqa: BLE001
        print("cannot load site list %s (%s) — skip" % (SITE_LIST, e))
        return 0
    if not sites:
        print("empty site list — skip")
        return 0

    lat, lon, source = _resolve_location()
    site = nearest_site(lat, lon, sites)
    if not site:
        print("no nearest site — skip")
        return 0

    xml_text = _fetch_site_xml(site["prov"], site["code"])
    if xml_text is None:
        print("EC unreachable for %s/%s — keeping last cache" % (site["prov"], site["code"]))
        return 0
    try:
        parsed = parse_citypage(xml_text)
    except Exception as e:  # noqa: BLE001
        print("parse failed for %s (%s) — keeping last cache" % (site["code"], e))
        return 0
    if not parsed or parsed.get("temp_c") is None:
        print("no usable current temp for %s — keeping last cache" % site["code"])
        return 0

    cache = {"schemaVersion": 1, "fetched_ts": int(time.time()),
             "site": site["code"], "prov": site["prov"]}
    cache.update(parsed)
    if not cache.get("location"):        # prefer the XML's display name; fall back to the CSV name
        cache["location"] = site["name"]
    _atomic_write_json(WEATHER_JSON, cache)
    print("weather cached: %s %s°C (%s, via %s) -> %s"
          % (cache.get("location"), cache.get("temp_c"), cache.get("condition"), source, WEATHER_JSON))
    return 0


if __name__ == "__main__":
    sys.exit(main())
