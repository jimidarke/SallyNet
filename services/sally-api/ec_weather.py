"""ec_weather.py — Environment Canada City Page Weather: nearest-site lookup + XML parse.

Pure, stdlib-only (csv, math, xml.etree) so it runs on the Pi's EOL Buster and is trivially
unit-tested. The weather worker (scripts/weather-refresh.py) imports this from the deployed
sally-api dir (the same sys.path trick waypoint-eta-refresh.py uses for select_next_waypoint);
/api/state only READS the JSON the worker writes, so app.py does not import this module.

Data source: https://dd.weather.gc.ca/today/citypage_weather/  (City Page Weather XML, no API key).
Site table: ec_sites.csv, distilled from EC's site_list_en.geojson (signed-decimal lat/lon).
EC data + icons are Open Government Licence - Canada; attribute "Environment and Climate Change Canada".
"""
import csv
import math
import xml.etree.ElementTree as ET


def load_sites(path):
    """Load the distilled EC site table -> list of {code, prov, name, lat, lon}."""
    sites = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                sites.append({"code": row["code"], "prov": row["prov"], "name": row["name"],
                              "lat": float(row["lat"]), "lon": float(row["lon"])})
            except (KeyError, ValueError):
                continue
    return sites


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_site(lat, lon, sites):
    """Nearest EC site to (lat, lon), or None if the table is empty."""
    best, best_km = None, None
    for s in sites:
        km = _haversine_km(lat, lon, s["lat"], s["lon"])
        if best_km is None or km < best_km:
            best, best_km = s, km
    return best


def _text(el, path):
    """Stripped text of el.find(path), or None when missing/empty (EC leaves tags empty, not absent)."""
    if el is None:
        return None
    x = el.find(path)
    if x is None or x.text is None:
        return None
    return x.text.strip() or None


def _to_int(s):
    if s is None:
        return None
    try:
        return int(round(float(s)))
    except (TypeError, ValueError):
        return None


def _obs_hm(cc):
    """Local-zone observation time as 'HH:MM'. EC ships two <dateTime name="observation"> children
    (UTC + local); prefer the local one, fall back to UTC only if that's all there is."""
    if cc is None:
        return None
    utc_only = None
    for dt in cc.findall("dateTime"):
        if dt.get("name") != "observation":
            continue
        hh, mm = dt.findtext("hour"), dt.findtext("minute")
        if not hh or not mm:
            continue
        cand = "%s:%s" % (hh.zfill(2), mm.zfill(2))
        if (dt.get("zone") or "").upper() not in ("UTC", "Z"):
            return cand          # local zone — what we want to display
        utc_only = utc_only or cand
    return utc_only


def parse_citypage(xml_text):
    """Parse an EC citypage weather XML document into the compact weather dict, or None if it lacks
    a usable current temperature. Two real-world fallbacks (both observed in live EC data):
      * currentConditions condition/iconCode are frequently EMPTY -> fall back to the current
        forecast period's abbreviatedForecast icon/text.
      * today's high & low: take the first class='high' and first class='low' scanning the leading
        forecasts, because the Today/Tonight period order flips between morning and evening.
    """
    root = ET.fromstring(xml_text)

    location = _text(root.find("location"), "name")

    cc = root.find("currentConditions")
    temp_c = _to_int(_text(cc, "temperature"))
    condition = _text(cc, "condition")
    icon = _text(cc, "iconCode")
    observed_hm = _obs_hm(cc)

    fg = root.find("forecastGroup")
    forecasts = fg.findall("forecast") if fg is not None else []
    high_c = low_c = summary = fc_icon = fc_cond = None
    for i, fc in enumerate(forecasts[:4]):
        for tmp in fc.iter("temperature"):        # temps live under <temperatures>; iter is safe
            cls = tmp.get("class")
            if cls == "high" and high_c is None:
                high_c = _to_int(tmp.text)
            elif cls == "low" and low_c is None:
                low_c = _to_int(tmp.text)
        if i == 0:
            summary = _text(fc, "textSummary")
            ab = fc.find("abbreviatedForecast")
            fc_icon = _text(ab, "iconCode")
            fc_cond = _text(ab, "textSummary")

    if not icon:
        icon = fc_icon
    if not condition:
        condition = fc_cond

    if temp_c is None:
        return None
    return {
        "temp_c": temp_c,
        "condition": condition,
        "icon": icon,
        "high_c": high_c,
        "low_c": low_c,
        "summary": summary,
        "location": location,
        "observed_hm": observed_hm,
    }
