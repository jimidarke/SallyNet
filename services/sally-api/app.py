#!/usr/bin/env python3
"""sally-api — the single HTTP surface the Roku dashboard polls.

Phase 0: live `/api/state` from gpsd + `/api/health` + `/api/discovery` (stub).
Sensor sections (power/tanks/env/level/cameras/audio) are `null` placeholders until
later phases fill them via the MQTT collector / go2rtc. Runs on its own port (:8090)
so it never touches the existing :80 metrics app.
"""
import io
import json
import math
import mimetypes
import os
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime

from flask import Flask, Response, abort, jsonify, request, send_file
from werkzeug.utils import secure_filename

import sallyconf as cfg
import store
import studio_index
import trail
import waypoints as waypoints_mod
from gpsd_client import read_fix

# Map compositor (needs Pillow). Imported optionally so a host without Pillow still boots the
# rest of the API — /api/map.png just 501s. Pillow is in requirements.txt and present on the Pi.
try:
    import tiles
    import mapgen
    _MAP_OK = True
except ImportError:
    _MAP_OK = False

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = cfg.UPLOAD_MAX_BYTES
_BOOT = time.time()

# Mobile-first guest upload page. Self-contained (no external assets — guests may be on
# cellular). Populates the trip picker from /api/media?type=trips and can attach the
# phone's GPS so photos without embedded location still get geotagged.
_UPLOAD_HTML = """<!doctype html><html lang=en><head>
<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Send photos to Sally</title><style>
:root{--g:#d4a017;--r:#c0392b;--o:#e67e22;--ink:#2b2b2b}
*{box-sizing:border-box}body{font-family:system-ui,sans-serif;margin:0;background:#faf7f0;color:var(--ink)}
header{background:var(--g);padding:18px 16px;border-bottom:4px solid var(--r)}
h1{margin:0;font-size:1.25rem}main{padding:16px;max-width:560px;margin:0 auto}
label{display:block;margin:14px 0 4px;font-weight:600}
input,select,button{width:100%;padding:12px;font-size:1rem;border:1px solid #ccc;border-radius:8px}
button{background:var(--r);color:#fff;border:0;font-weight:700;margin-top:18px}
button:disabled{opacity:.5}.row{display:flex;gap:8px;align-items:center;margin-top:10px}
.row input[type=checkbox]{width:auto}.hint{color:#777;font-size:.85rem;margin-top:4px}
#out{margin-top:16px;padding:12px;border-radius:8px;display:none}
.ok{background:#e8f5e9}.err{background:#fdecea}#newtrip{display:none}
progress{width:100%;height:14px}
</style></head><body>
<header><h1>📷 Send your photos &amp; videos to Sally</h1></header><main>
<form id=f>
<label>Which trip?</label>
<select id=trip><option value=unsorted>Unsorted (sort later)</option>
<option value=new>➕ New trip…</option></select>
<input id=newtrip placeholder="New trip name">
<label>Your name (optional)</label><input id=uploader placeholder="e.g. Aunt Robin">
<label>Photos &amp; videos</label>
<input id=files type=file multiple accept="image/*,video/*">
<div class=row><input type=checkbox id=geo><label for=geo style="margin:0;font-weight:400">
Attach my phone's location (helps tag photos without GPS)</label></div>
<button id=go type=submit>Upload</button>
<progress id=pg max=100 value=0 style=display:none></progress>
</form><div id=out></div></main><script>
var tripSel=document.getElementById('trip'),nt=document.getElementById('newtrip');
fetch('/api/media?type=trips').then(r=>r.json()).then(d=>{(d.collections||[]).forEach(c=>{
 if(c.kind!=='trip')return;var o=document.createElement('option');o.value=c.id;o.textContent=c.title;
 tripSel.insertBefore(o,tripSel.lastChild);});}).catch(()=>{});
tripSel.onchange=()=>{nt.style.display=tripSel.value==='new'?'block':'none';};
var out=document.getElementById('out'),pg=document.getElementById('pg'),go=document.getElementById('go');
document.getElementById('f').onsubmit=function(e){e.preventDefault();
 var fs=document.getElementById('files').files;if(!fs.length){show(false,'Pick some photos or videos first.');return;}
 var fd=new FormData();for(var i=0;i<fs.length;i++)fd.append('files',fs[i]);
 fd.append('uploader',document.getElementById('uploader').value);
 fd.append('trip',tripSel.value);if(tripSel.value==='new')fd.append('tripTitle',nt.value);
 function send(){var x=new XMLHttpRequest();x.open('POST','/api/upload');
  pg.style.display='block';go.disabled=true;
  x.upload.onprogress=function(ev){if(ev.lengthComputable)pg.value=ev.loaded/ev.total*100;};
  x.onload=function(){go.disabled=false;pg.style.display='none';try{var r=JSON.parse(x.responseText);
   if(r.ok)show(true,'Thanks! Sent '+r.accepted.length+' item(s). Sally will add them soon.');
   else show(false,'Upload failed: '+(r.error||(r.rejected&&r.rejected.length?'unsupported files':'try again')));}
   catch(_){show(false,'Upload failed ('+x.status+').');}};
  x.onerror=function(){go.disabled=false;pg.style.display='none';show(false,'Network error — are you on SallyNet Wi-Fi?');};
  x.send(fd);}
 if(document.getElementById('geo').checked&&navigator.geolocation){
  navigator.geolocation.getCurrentPosition(function(p){fd.append('lat',p.coords.latitude);
   fd.append('lon',p.coords.longitude);send();},function(){send();},{timeout:8000});
 }else send();};
function show(ok,msg){out.style.display='block';out.className=ok?'ok':'err';out.textContent=msg;}
</script></body></html>"""

# Driver/navigator trip-entry page (C2). Creates the active trip: its destination drives
# the "camping" geofence + Drive-screen ETA, and it auto-creates the matching media
# collection so guest photo uploads route to the right trip from day one.
_TRIP_HTML = """<!doctype html><html lang=en><head>
<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Sally — Plan a trip</title><style>
:root{--g:#d4a017;--r:#c0392b;--o:#e67e22;--ink:#2b2b2b}
*{box-sizing:border-box}body{font-family:system-ui,sans-serif;margin:0;background:#faf7f0;color:var(--ink)}
header{background:var(--g);padding:18px 16px;border-bottom:4px solid var(--r)}
h1{margin:0;font-size:1.25rem}main{padding:16px;max-width:560px;margin:0 auto}
label{display:block;margin:14px 0 4px;font-weight:600}
input,button{width:100%;padding:12px;font-size:1rem;border:1px solid #ccc;border-radius:8px}
button{background:var(--r);color:#fff;border:0;font-weight:700;margin-top:18px}
button.alt{background:#555;margin-top:10px}button:disabled{opacity:.5}
.two{display:flex;gap:10px}.two>div{flex:1}
.row{display:flex;gap:8px;align-items:center;margin-top:10px}.row input[type=checkbox]{width:auto}
.hint{color:#777;font-size:.85rem;margin-top:4px}
#cur{background:#eef;padding:10px;border-radius:8px;margin-bottom:8px;font-size:.9rem}
#out{margin-top:16px;padding:12px;border-radius:8px;display:none}.ok{background:#e8f5e9}.err{background:#fdecea}
</style></head><body>
<header><h1>🧭 Plan a trip in Sally</h1></header><main>
<div id=cur></div>
<form id=f>
<label>Trip name</label><input id=title placeholder="e.g. Jasper &amp; the Icefields" required>
<label>Destination</label><input id=dest placeholder="e.g. Jasper, AB">
<div class=row><input type=checkbox id=pin><label for=pin style="margin:0;font-weight:400">
Can't find it / no signal — pin Sally's current GPS as the destination</label></div>
<label>Who's aboard?</label><input id=aboard placeholder="comma separated, e.g. Jimi, Alex, kids">
<div class=two><div><label>Start date</label><input id=ds type=date></div>
<div><label>End date</label><input id=de type=date></div></div>
<button id=go type=submit>Save &amp; start trip</button>
<button id=end type=button class=alt>End current trip</button>
</form><div id=out></div></main><script>
var out=document.getElementById('out'),go=document.getElementById('go');
function show(ok,msg){out.style.display='block';out.className=ok?'ok':'err';out.textContent=msg;}
function refresh(){fetch('/api/trip').then(r=>r.json()).then(d=>{
 var c=document.getElementById('cur');
 if(d.activeTripId&&d.trips&&d.trips[d.activeTripId]){var t=d.trips[d.activeTripId];
  c.textContent='Active trip: '+t.title+(t.destName?(' → '+t.destName):'')+(t.dest?'  📍':'  (no map pin yet)');}
 else{c.textContent='No active trip.';}}).catch(()=>{});}
refresh();
document.getElementById('f').onsubmit=function(e){e.preventDefault();
 var title=document.getElementById('title').value.trim();
 if(!title){show(false,'Give the trip a name.');return;}
 var fd=new FormData();fd.append('title',title);
 fd.append('destName',document.getElementById('dest').value.trim());
 fd.append('aboard',document.getElementById('aboard').value);
 fd.append('dateStart',document.getElementById('ds').value);
 fd.append('dateEnd',document.getElementById('de').value);
 function send(){go.disabled=true;fetch('/api/trip',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
  go.disabled=false;
  if(d.ok)show(true,'Trip saved'+(d.dest?(' with map pin.'):' (no map pin — '+(d.destReason||'add a destination')+').'));
  else show(false,'Could not save: '+(d.error||'try again'));refresh();})
  .catch(()=>{go.disabled=false;show(false,'Network error — are you on SallyNet Wi-Fi?');});}
 if(document.getElementById('pin').checked&&navigator.geolocation){
  navigator.geolocation.getCurrentPosition(function(p){fd.append('pin','1');
   fd.append('lat',p.coords.latitude);fd.append('lon',p.coords.longitude);send();},
   function(){fd.append('pin','1');send();},{timeout:8000});
 }else send();};
document.getElementById('end').onclick=function(){
 var fd=new FormData();fd.append('end','1');
 fetch('/api/trip',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
  show(true,'Trip ended.');refresh();}).catch(()=>show(false,'Network error.'));};
</script></body></html>"""


# Driver fuel/mileage logger (C3). Plain numeric entry — the phone's native number pad
# (inputmode=decimal) keeps it one-handed at the pump; the same fields map onto the
# eventual ESP32 keypad. datetime + GPS are stamped server-side.
_FUEL_HTML = """<!doctype html><html lang=en><head>
<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Sally — Fuel log</title><style>
:root{--g:#d4a017;--r:#c0392b;--o:#e67e22;--ink:#2b2b2b}
*{box-sizing:border-box}body{font-family:system-ui,sans-serif;margin:0;background:#faf7f0;color:var(--ink)}
header{background:var(--g);padding:18px 16px;border-bottom:4px solid var(--r)}
h1{margin:0;font-size:1.25rem}main{padding:16px;max-width:560px;margin:0 auto}
label{display:block;margin:14px 0 4px;font-weight:600}
input,button{width:100%;padding:14px;font-size:1.15rem;border:1px solid #ccc;border-radius:8px}
button{background:var(--r);color:#fff;border:0;font-weight:700;margin-top:18px}button:disabled{opacity:.5}
.hint{color:#777;font-size:.85rem;margin-top:4px}
#last{background:#eef;padding:10px;border-radius:8px;margin-bottom:8px;font-size:.9rem}
#out{margin-top:16px;padding:12px;border-radius:8px;display:none}.ok{background:#e8f5e9}.err{background:#fdecea}
</style></head><body>
<header><h1>⛽ Sally fuel log</h1></header><main>
<div id=last></div>
<form id=f>
<label>Odometer (km)</label>
<input id=odo type=text inputmode=decimal placeholder="e.g. 142357">
<label>Litres filled</label>
<input id=litres type=text inputmode=decimal placeholder="e.g. 87.4">
<label>Price per litre ($)</label>
<input id=price type=text inputmode=decimal placeholder="e.g. 1.62">
<button id=go type=submit>Save fill-up</button>
<div class=hint>Date, time &amp; location are added automatically.</div>
</form><div id=out></div></main><script>
var out=document.getElementById('out'),go=document.getElementById('go');
function show(ok,msg){out.style.display='block';out.className=ok?'ok':'err';out.textContent=msg;}
function refresh(){fetch('/api/state').then(r=>r.json()).then(s=>{
 var l=document.getElementById('last');
 if(s.fuel&&s.fuel.last){var f=s.fuel.last;var t='Last fill: '+f.litres+' L';
  if(f.l_100km)t+=' · '+f.l_100km+' L/100km';
  if(s.fuel.avg_l_100km)t+=' · avg '+s.fuel.avg_l_100km;l.textContent=t;}
 else l.textContent='No fill-ups logged yet.';}).catch(()=>{});}
refresh();
document.getElementById('f').onsubmit=function(e){e.preventDefault();
 var fd=new FormData();
 fd.append('odo',document.getElementById('odo').value);
 fd.append('litres',document.getElementById('litres').value);
 fd.append('price',document.getElementById('price').value);
 go.disabled=true;fetch('/api/fuel-log',{method:'POST',body:fd}).then(r=>r.json()).then(d=>{
  go.disabled=false;
  if(d.ok){var m='Logged '+d.entry.litres+' L for $'+d.entry.total_cost;
   if(d.entry.l_100km)m+=' — '+d.entry.l_100km+' L/100km this tank.';
   show(true,m);document.getElementById('f').reset();refresh();}
  else show(false,'Could not save: '+(d.error||'check the numbers'));})
  .catch(()=>{go.disabled=false;show(false,'Network error — are you on SallyNet Wi-Fi?');});};
</script></body></html>"""


# Cached readers for the trip store + OSRM route cache (mtime-checked per request).
_movies = store.CachedJson(cfg.MOVIES_JSON, {"collections": [], "items": {}})
_trips = store.CachedJson(cfg.TRIPS_JSON, {"activeTripId": None, "trips": {}})
_route = store.CachedJson(cfg.ROUTE_JSON, {})
_fuel = store.CachedJson(cfg.FUEL_LOG_JSON, {"entries": []})
_waypoints = store.CachedJson(cfg.WAYPOINTS_JSON, {"waypoints": []})
_wproute = store.CachedJson(cfg.WAYPOINT_ROUTE_JSON, {})
_poi = store.CachedJson(cfg.POI_CACHE_JSON, {"regions": []})
_photo_poi = store.CachedJson(cfg.PHOTO_POI_JSON, {"photos": []})
_trail = trail.TrailCache(cfg.TRACKS_DIR)

# Shared, persisted map view-state: the layer set every viewer + the Roku glass renders. The
# default carries no `layers` so a fresh install falls back to "all layers"; _DEFAULT_LAYERS is
# only the no-Pillow fallback layer set (mapgen is the live SSOT when it imported).
_DEFAULT_LAYERS = ("base", "trail", "poi", "photos", "waypoints", "labels", "status")
_view = store.CachedJson(cfg.VIEW_STATE_JSON, {"schemaVersion": cfg.SCHEMA_VERSION})

# GPS-loss tracking: the nav-tick read-model (nav-state.json) is primary — fresh even when nobody
# polls; the in-process _last_good tracker is the fallback when nav-tick is off but someone polls.
_nav = store.CachedJson(cfg.NAV_STATE_JSON, {})
_last_good = {"ts": 0.0, "lat": None, "lon": None, "speed_kmh": None}


def _all_layers():
    """The valid layer names — the live mapgen set, or the literal fallback without Pillow."""
    return set(mapgen.ALL_LAYERS) if _MAP_OK else set(_DEFAULT_LAYERS)


def _view_state():
    """Shared view state with defaults filled + layers validated against the live layer set.
    Empty/missing layers fall back to ALL layers (a fresh install shows everything)."""
    vs = _view.get() or {}
    allset = _all_layers()
    layers = [l for l in (vs.get("layers") or []) if l in allset]
    if not layers:
        layers = sorted(allset)
    return {"layers": layers, "baseSource": vs.get("baseSource") or "street",
            "updatedTs": vs.get("updatedTs")}

# Shared short-TTL GPS fix. /api/state and /api/map.png both poll on the Roku's cadence;
# without this each does its own ~2.5 s gpsd read and doubles the load. The lock makes a
# cold-cache refresh single-flight so concurrent requests coalesce onto one read.
_fix_lock = threading.Lock()
_fix_cache = {"fix": None, "at": 0.0}
_FIX_TTL_S = 2.0


def _cached_fix():
    """The most recent gpsd fix, re-read at most every _FIX_TTL_S seconds."""
    now = time.time()
    if _fix_cache["fix"] is not None and (now - _fix_cache["at"]) < _FIX_TTL_S:
        return _fix_cache["fix"]
    with _fix_lock:
        now = time.time()
        if _fix_cache["fix"] is not None and (now - _fix_cache["at"]) < _FIX_TTL_S:
            return _fix_cache["fix"]
        fix = read_fix(cfg.GPSD_HOST, cfg.GPSD_PORT)
        _track_fix(fix)
        _fix_cache["fix"] = fix
        _fix_cache["at"] = time.time()
        return fix


def _track_fix(fix):
    """Remember the last good fix in-process so /api/map.png can report a fix-age even when the
    nav-tick daemon isn't running (it just needs someone to be polling gpsd via _cached_fix)."""
    if fix.get("fix") and fix.get("lat") is not None:
        _last_good.update(ts=time.time(), lat=fix["lat"], lon=fix["lon"],
                          speed_kmh=fix.get("speed_kmh"))


def _fix_age_and_last(gps):
    """(secondsSinceFix, last_known, had_fix). Prefer the nav-tick read-model (fresh even with no
    polling); fall back to the in-process tracker; finally 'never had a fix this session'."""
    now = time.time()
    if gps.get("fix") and gps.get("lat") is not None:
        return 0, {"lat": gps["lat"], "lon": gps["lon"], "speed_kmh": gps.get("speed_kmh")}, True
    nav = _nav.get() or {}
    if nav.get("ts") and (now - nav["ts"]) < cfg.NAV_STATE_STALE_S:
        return nav.get("secondsSinceFix"), nav.get("lastKnown") or {}, bool(nav.get("hadFix"))
    if _last_good["lat"] is not None:
        return int(now - _last_good["ts"]), dict(_last_good), True
    return int(now - _BOOT), {}, False


def _active_trip():
    """Return the active trip dict (with dest/aboard/etc.) or None."""
    data = _trips.get()
    tid = data.get("activeTripId")
    if not tid:
        return None
    return (data.get("trips") or {}).get(tid)


def _geocode(name):
    """Best-effort OSM Nominatim geocode -> (lat, lon) or None (offline/unmatched)."""
    if not name:
        return None
    try:
        url = cfg.NOMINATIM_URL + "?" + urllib.parse.urlencode(
            {"q": name, "format": "json", "limit": 1})
        req = urllib.request.Request(url, headers={"User-Agent": cfg.GEO_USER_AGENT})
        with urllib.request.urlopen(req, timeout=8) as r:
            hits = json.loads(r.read().decode())
        if hits:
            return float(hits[0]["lat"]), float(hits[0]["lon"])
    except Exception:
        return None
    return None


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _throttled():
    try:
        out = subprocess.check_output(["vcgencmd", "get_throttled"], timeout=2)
        return out.decode().strip().split("=")[-1]
    except Exception:
        return None


def _prune(obj):
    """Recursively drop None so /api/state never emits JSON null. The Roku stores
    state in SceneGraph assocarray fields, which mishandle `invalid` values; omitting
    keys (the Roku reads a missing key back as invalid -> widget hidden) keeps the
    cross-thread round-trip clean. Empty lists/dicts are preserved."""
    if isinstance(obj, dict):
        return {k: _prune(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_prune(v) for v in obj]
    return obj


def _derive_mode(gps, km_from_home, km_to_dest):
    """Instantaneous mode hint (the Roku applies hysteresis). `camping` requires an
    active trip with a destination pin we're stopped within — it can't be inferred
    from GPS alone, which is why a generic stop is `parked`, not `camping`."""
    if not gps["fix"]:
        return "unknown"
    if (gps["speed_kmh"] or 0) >= cfg.DRIVING_KMH:
        return "driving"
    if km_from_home is not None and km_from_home * 1000.0 <= cfg.HOME_RADIUS_M:
        return "at_home"
    if km_to_dest is not None and km_to_dest * 1000.0 <= cfg.DEST_RADIUS_M:
        return "camping"
    return "parked"


def _trip_state(active, km_to_dest):
    """Project the active trip into the /api/state `trip` section. ETA comes from the
    OSRM route cache (scripts/trip-eta-refresh.py) when fresh; km_to_dest (haversine)
    is always present so something shows offline."""
    section = {
        "id": active.get("id"),
        "title": active.get("title"),
        "destName": active.get("destName"),
        "dest": active.get("dest"),
        "aboard": active.get("aboard"),
        "dateStart": active.get("dateStart"),
        "dateEnd": active.get("dateEnd"),
        "km_to_dest": km_to_dest,
    }
    route = _route.get()
    if route and route.get("tripId") == active.get("id") and route.get("eta_epoch"):
        section["eta"] = int(route["eta_epoch"])           # arrival, unix seconds UTC
        section["roadKm"] = route.get("road_km")
        section["etaSource"] = "osrm"
        section["etaStaleSec"] = max(0, int(time.time()) - int(route.get("computed_at", 0)))
    return section


def _fuel_state():
    """Project the fuel log into the /api/state `fuel` section: last fill + the
    running average economy. None when nothing's been logged."""
    entries = (_fuel.get() or {}).get("entries") or []
    if not entries:
        return None
    last = entries[-1]
    econ = [e["l_100km"] for e in entries if e.get("l_100km")]
    avg = round(sum(econ) / len(econ), 1) if econ else None
    return {
        "last": {
            "date": last.get("datetime"),
            "odo_km": last.get("odo_km"),
            "litres": last.get("litres"),
            "total": last.get("total_cost"),
            "l_100km": last.get("l_100km"),
        },
        "avg_l_100km": avg,
        "fills": len(entries),
    }


# =============================================================================
# Home media (P1/P5) — catalog endpoints, byte-range file serving, QR + upload.
# The Roku is glass: it reads catalog.json (rebuilt by media-reindex.py) sliced into
# the shapes below, plays /media/<path>, shows /api/qr.png, and guests POST /api/upload.
# =============================================================================
_catalog = {"mtime": -1.0, "data": {"collections": [], "items": {}, "photos": []}}


def _load_catalog():
    """Return catalog.json, reloading only when its mtime changes (cheap per-request)."""
    try:
        mtime = os.stat(cfg.CATALOG_JSON).st_mtime
    except OSError:
        return _catalog["data"]
    if mtime != _catalog["mtime"]:
        try:
            with open(cfg.CATALOG_JSON) as f:
                _catalog["data"] = json.load(f)
            _catalog["mtime"] = mtime
        except (ValueError, OSError):
            pass
    return _catalog["data"]


def _trip_stub(t):
    """A zero-item browse collection for a trip that's been planned but has no media yet
    (catalog.json only lists collections that have items). Lets a freshly-created trip
    appear in the upload form's picker immediately, before any reindex."""
    return _prune({
        "id": t["id"], "kind": "trip", "title": t.get("title") or t["id"],
        "itemCount": 0, "videoCount": 0, "photoCount": 0,
        "dateStart": t.get("dateStart"), "dateEnd": t.get("dateEnd"),
        "place": t.get("place") or t.get("destName"),
        "detailUrl": "/api/collections/" + t["id"],
    })


@app.route("/api/media")
def api_media():
    """type=trips -> home collections. type=movies -> studio library (Workstream A).
    type=tv|kids -> reserved, still empty (tv lands in a later phase; kids is a per-item
    kidSafe flag, not its own catalog)."""
    t = request.args.get("type", "trips")
    if t == "movies":
        m = _movies.get()
        return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "type": t,
                         "collections": m.get("collections", [])})
    if t != "trips":
        return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "type": t, "collections": []})
    cat = _load_catalog()
    cols = list(cat.get("collections", []))
    have = {c.get("id") for c in cols}
    # Surface planned-but-empty trips from the store (not yet in the reindexed catalog).
    for cid, trip in (_trips.get().get("trips") or {}).items():
        if cid not in have and trip.get("id"):
            cols.append(_trip_stub(trip))
    cols.sort(key=lambda c: c.get("dateStart") or "", reverse=True)
    return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "type": t, "collections": cols})


@app.route("/api/collections/<cid>")
def api_collection(cid):
    movies_cat = _movies.get()
    movie_items = movies_cat.get("items", {}).get(cid)
    if movie_items is not None:
        meta = next((c for c in movies_cat.get("collections", []) if c.get("id") == cid), {})
        return jsonify(_prune({
            "schemaVersion": cfg.SCHEMA_VERSION, "id": cid, "kind": meta.get("kind"),
            "title": meta.get("title"), "items": movie_items,
        }))
    cat = _load_catalog()
    items = cat.get("items", {}).get(cid)
    if items is None:
        # A planned-but-empty trip drills into an empty (not missing) collection.
        trip = (_trips.get().get("trips") or {}).get(cid)
        if trip:
            return jsonify(_prune({
                "schemaVersion": cfg.SCHEMA_VERSION, "id": cid, "kind": "trip",
                "title": trip.get("title"), "dateStart": trip.get("dateStart"),
                "dateEnd": trip.get("dateEnd"),
                "place": trip.get("place") or trip.get("destName"), "items": [],
            }))
        abort(404)
    meta = next((c for c in cat.get("collections", []) if c.get("id") == cid), {})
    return jsonify(_prune({
        "schemaVersion": cfg.SCHEMA_VERSION,
        "id": cid, "kind": meta.get("kind"), "title": meta.get("title"),
        "dateStart": meta.get("dateStart"), "dateEnd": meta.get("dateEnd"),
        "place": meta.get("place"), "items": items,
    }))


@app.route("/api/photos")
def api_photos():
    cat = _load_catalog()
    photos = cat.get("photos", [])
    coll = request.args.get("collection")
    if coll:
        photos = [p for p in photos if p.get("collectionId") == coll]
    return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "photos": photos})


_STUDIO_DIRS = {"movies", "tv"}


def _safe_media_path(relpath):
    """Resolve relpath under MEDIA_ROOT (trips/drone/unsorted, unchanged) or STUDIO_ROOT
    (movies/tv), rejecting traversal. Two roots, not one broadened root, specifically so
    broadening studio coverage can never shift where an existing Trips URL resolves."""
    top = relpath.split("/", 1)[0]
    base = cfg.STUDIO_ROOT if top in _STUDIO_DIRS else cfg.MEDIA_ROOT
    root = os.path.realpath(base)
    full = os.path.realpath(os.path.join(root, relpath))
    if full != root and not full.startswith(root + os.sep):
        abort(403)
    if not os.path.isfile(full):
        abort(404)
    return full


_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)\s*$")


@app.route("/media/<path:relpath>")
def media_file(relpath):
    """Byte-serve the library with explicit HTTP Range support (Roku MP4 seeking needs
    206/Accept-Ranges; implemented directly so it works on Buster's old Werkzeug too)."""
    full = _safe_media_path(relpath)
    size = os.path.getsize(full)
    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    rng = request.headers.get("Range")

    start, end = 0, size - 1
    status = 200
    if rng:
        m = _RANGE_RE.match(rng)
        if not m:
            r = Response(status=416)
            r.headers["Content-Range"] = "bytes */%d" % size
            return r
        s, e = m.group(1), m.group(2)
        if s == "" and e == "":
            abort(416)
        elif s == "":                       # suffix: last N bytes
            start, end = max(0, size - int(e)), size - 1
        else:
            start = int(s)
            end = int(e) if e else size - 1
        if start >= size or start > end:
            r = Response(status=416)
            r.headers["Content-Range"] = "bytes */%d" % size
            return r
        end = min(end, size - 1)
        status = 206

    length = end - start + 1

    # Smaller than waitress 1.2.0b2's 1 MiB outbuf_overflow threshold, by a wide margin —
    # keeps less data in flight so a slow/seeking client is far less likely to trip
    # waitress's disk-spool buffering, which has a known disconnect-time race (closes its
    # spool file out from under a write already in flight: github.com/Pylons/waitress/
    # issues/116). Mitigation, not a full fix — that needs a waitress upgrade, out of
    # scope while this Pi stays on Buster.
    def stream(path=full, start=start, length=length, chunk=65536):
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                buf = f.read(min(chunk, remaining))
                if not buf:
                    break
                remaining -= len(buf)
                yield buf

    resp = Response(stream(), status=status, mimetype=ctype, direct_passthrough=True)
    resp.headers["Accept-Ranges"] = "bytes"
    resp.headers["Content-Length"] = str(length)
    if status == 206:
        resp.headers["Content-Range"] = "bytes %d-%d/%d" % (start, end, size)
    return resp


_qr_cache = {}


@app.route("/api/qr.png")
def api_qr():
    """QR encoding the LAN upload URL guests scan from SallyNet WiFi."""
    url = cfg.LAN_BASE_URL.rstrip("/") + "/upload"
    if url not in _qr_cache:
        try:
            import qrcode  # noqa: WPS433 (optional dep; install on the host)
        except ImportError:
            abort(501)
        img = qrcode.make(url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        _qr_cache[url] = buf.getvalue()
    return Response(_qr_cache[url], mimetype="image/png")


# =============================================================================
# Ambient map (P2) — /api/map.png. mapgen.py bakes one PNG from live GPS + cached tiles +
# the breadcrumb/waypoint/POI layers; the Roku just displays it. The server owns the centre
# (live GPS) and the speed-based zoom, so the Roku can fetch with no params at all.
# See subsystems/gps/map-navigation-brainstorm.md.
# =============================================================================

def _map_center_zoom(gps, last_known, args):
    """Centre = live GPS; on no-fix FREEZE at the last-known position (teleporting to the home
    anchor mid-trip is confusing) and freeze the last zoom band; the home anchor is used only when
    we never had a fix. An undocumented ?center=lat,lon override exists for offline/demo rendering."""
    center = (cfg.HOME_LAT, cfg.HOME_LON)
    if gps.get("fix") and gps.get("lat") is not None:
        center = (gps["lat"], gps["lon"])
    elif last_known.get("lat") is not None:
        center = (last_known["lat"], last_known["lon"])
    c = args.get("center")
    if c:
        try:
            lat, lon = c.split(",")
            center = (float(lat), float(lon))
        except (ValueError, TypeError):
            pass
    z = args.get("z", "auto")
    if z in ("auto", "", None):
        spd, has_fix = gps.get("speed_kmh"), bool(gps.get("fix"))
        if not has_fix and last_known.get("speed_kmh") is not None:
            spd, has_fix = last_known["speed_kmh"], True  # freeze the last band, don't snap tight
        zoom = tiles.speed_to_zoom(spd, has_fix=has_fix)
    else:
        try:
            zoom = max(tiles.ZOOM_MIN, min(tiles.ZOOM_MAX, int(z)))
        except (ValueError, TypeError):
            zoom = tiles.speed_to_zoom(gps.get("speed_kmh"), has_fix=bool(gps.get("fix")))
    return center, zoom


def _parse_layers(arg, default_layers):
    """Explicit ?layers= CSV is a one-off override (debugging); with no param the SHARED,
    persisted view-state set is used so the Roku and every browser converge on the same layers."""
    allset = set(mapgen.ALL_LAYERS)
    if not arg:
        return (set(default_layers) & allset) or allset
    want = set(s.strip() for s in arg.split(",") if s.strip()) & allset
    return want or (set(default_layers) & allset) or allset


def _next_waypoint(gps, wlist):
    """The emphasised 'next' waypoint + distance for the status strip. Straight-line km always
    (offline-safe); upgraded to road-km/ETA when the OSRM cache (waypoint-eta-refresh.py) is
    fresh for this same waypoint."""
    sel = waypoints_mod.select_next_waypoint(wlist, gps.get("lat"), gps.get("lon"))
    if not sel:
        return None
    w, km = sel
    out = {"id": w.get("id"), "name": w.get("name"), "type": w.get("type"),
           "lat": w.get("lat"), "lon": w.get("lon"), "km": km}
    rt = _wproute.get()
    if (rt and rt.get("wpId") == w.get("id") and rt.get("road_km") is not None
            and int(time.time()) - int(rt.get("computed_at", 0)) <= cfg.ROUTE_STALE_S):
        out["km"] = rt["road_km"]
        out["eta"] = rt.get("eta_epoch")
    return out


def _map_data(gps):
    """Dynamic layers for the compositor (trail, waypoints + the emphasised next one, POI)."""
    wdata = _waypoints.get()
    return {
        "trail": _trail.get(),
        "waypoints": wdata,
        "poi": _poi.get(),
        "photoPoi": _photo_poi.get(),
        "route": _route.get(),
        "nextWaypoint": _next_waypoint(gps, wdata.get("waypoints") or []),
    }


@app.route("/api/map.png")
def api_map():
    """Server-composited ambient map PNG centred on live GPS."""
    if not _MAP_OK:
        abort(501)
    gps = _cached_fix()
    age, last_known, had_fix = _fix_age_and_last(gps)
    center, zoom = _map_center_zoom(gps, last_known, request.args)
    try:
        w = int(request.args.get("w", cfg.MAP_W))
        h = int(request.args.get("h", cfg.MAP_H))
    except (ValueError, TypeError):
        w, h = cfg.MAP_W, cfg.MAP_H
    w = max(320, min(1920, w))
    h = max(240, min(1080, h))
    layers = _parse_layers(request.args.get("layers"), _view_state()["layers"])
    tele = dict(gps)  # copy so the shared _cached_fix object is never mutated
    tele["fix_age_s"] = age
    tele["had_fix"] = had_fix
    png = mapgen.render_map_png(center, zoom, w, h, layers, tele, _map_data(gps))
    return Response(png, mimetype="image/png")


# Browser viewer for the map PNG — an easy way to see the ambient map off the TV (phone/laptop
# on SallyNet or over WireGuard) for troubleshooting + usage. Manual refresh; the zoom is a
# per-request override, but the LAYER toggles POST to /api/view so the choice persists SERVER-SIDE
# and every viewer + the Roku glass converge on the same layers. Requests the same 1920x1080 the
# Roku does, so it shares the server render cache (no extra Pi load at rest).
_MAP_HTML = """<!doctype html><html lang=en><head>
<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Sally — Map</title><style>
:root{--r:#c0392b}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:#11130f;font-family:system-ui,sans-serif;display:flex;flex-direction:column}
#stage{flex:1;position:relative;min-height:0}
#map{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#11130f}
#err{position:absolute;inset:0;display:none;align-items:center;justify-content:center;color:#e8dcc8;padding:20px;text-align:center}
#bar{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;background:#1c1f26;color:#f0ece2;padding:10px 12px;font-size:.85rem;border-top:3px solid var(--r)}
#go{background:var(--r);color:#fff;border:0;border-radius:8px;padding:9px 16px;font-weight:700;font-size:.95rem}
#bar select{background:#2a2e36;color:#f0ece2;border:1px solid #444;border-radius:6px;padding:4px 6px}
#bar label{white-space:nowrap}.L{vertical-align:middle}#ts{color:#9fa6b2;margin-left:auto;font-size:.78rem}
</style></head><body>
<div id=stage><img id=map alt="Sally map"><div id=err>Map didn't load — is sally-api up on :8090?</div></div>
<div id=bar>
<button id=go>↻ Refresh</button>
<label>zoom <select id=z>
<option value=auto>auto</option><option>10</option><option>11</option><option>12</option><option>13</option><option>14</option><option>15</option>
</select></label>
<label><input type=checkbox class=L value=base> base</label>
<label><input type=checkbox class=L value=trail> trail</label>
<label><input type=checkbox class=L value=poi> poi</label>
<label><input type=checkbox class=L value=photos> photos</label>
<label><input type=checkbox class=L value=waypoints> waypts</label>
<label><input type=checkbox class=L value=labels> labels</label>
<label><input type=checkbox class=L value=status> status</label>
<span id=ts>loading…</span>
</div><script>
var img=document.getElementById('map'),err=document.getElementById('err'),ts=document.getElementById('ts');
function url(){
 var z=document.getElementById('z').value;
 return '/api/map.png?w=1920&h=1080&z='+z+'&v='+Date.now();  // layers come from shared /api/view
}
function load(){ts.textContent='loading…';
 var pre=new Image();
 pre.onload=function(){img.src=pre.src;err.style.display='none';
  ts.textContent='loaded '+new Date().toLocaleTimeString()+' · '+pre.naturalWidth+'×'+pre.naturalHeight;};
 pre.onerror=function(){err.style.display='flex';ts.textContent='load failed';};
 pre.src=url();}
function syncView(){
 var ls=[].filter.call(document.querySelectorAll('.L'),function(c){return c.checked;})
          .map(function(c){return c.value;}).join(',');
 fetch('/api/view',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
   body:'layers='+encodeURIComponent(ls)}).then(function(){load();});
}
document.getElementById('go').onclick=load;
document.getElementById('z').onchange=load;
[].forEach.call(document.querySelectorAll('.L'),function(c){c.onchange=syncView;});
fetch('/api/view').then(function(r){return r.json();}).then(function(d){
 var on={};(d.layers||[]).forEach(function(l){on[l]=1;});
 [].forEach.call(document.querySelectorAll('.L'),function(c){c.checked=!!on[c.value];});
 load();
}).catch(load);
</script></body></html>"""


@app.route("/map")
def map_page():
    """Browser viewer for the ambient map PNG (troubleshooting + off-TV usage)."""
    return Response(_MAP_HTML, mimetype="text/html")


# Trip waypoints editor (phone, on SallyNet WiFi). Canonical store is waypoints.json; the map
# draws pins + emphasises the "next" one + counts it down in the status strip.
_WAYPOINTS_HTML = """<!doctype html><html lang=en><head>
<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Sally — Waypoints</title><style>
:root{--g:#d4a017;--r:#c0392b;--o:#e67e22;--ink:#2b2b2b}
*{box-sizing:border-box}body{font-family:system-ui,sans-serif;margin:0;background:#faf7f0;color:var(--ink)}
header{background:var(--g);padding:18px 16px;border-bottom:4px solid var(--r)}
h1{margin:0;font-size:1.25rem}main{padding:16px;max-width:560px;margin:0 auto}
label{display:block;margin:14px 0 4px;font-weight:600}
input,select,button{width:100%;padding:12px;font-size:1rem;border:1px solid #ccc;border-radius:8px}
button{background:var(--r);color:#fff;border:0;font-weight:700;margin-top:18px}button:disabled{opacity:.5}
.row{display:flex;gap:8px;align-items:center;margin-top:10px}.row input[type=checkbox]{width:auto}
.hint{color:#777;font-size:.85rem;margin-top:4px}
.two{display:flex;gap:8px}.two>div{flex:1}
#list{margin-bottom:6px}
.wp{display:flex;justify-content:space-between;align-items:center;background:#fff;border:1px solid #e3ddd0;border-radius:8px;padding:10px 12px;margin-bottom:6px}
.wp.done{opacity:.55}.wp .n{font-weight:600}
.wp .a button{width:auto;display:inline;padding:6px 10px;margin:0 0 0 6px;background:#777}
.wp .a button.del{background:var(--r)}
#out{margin-top:16px;padding:12px;border-radius:8px;display:none}.ok{background:#e8f5e9}.err{background:#fdecea}
</style></head><body>
<header><h1>🧭 Sally waypoints</h1></header><main>
<div id=list>Loading…</div>
<form id=f>
<label>Name</label><input id=name placeholder="e.g. Nordegg fuel" required>
<label>Type</label>
<select id=type><option value=stop>Stop</option><option value=fuel>Fuel</option>
<option value=camp>Camp</option><option value=scenic>Scenic</option></select>
<div class=two><div><label>Latitude</label>
<input id=lat type=text inputmode=decimal placeholder="e.g. 52.8734"></div>
<div><label>Longitude</label>
<input id=lon type=text inputmode=decimal placeholder="e.g. -118.0814"></div></div>
<div class=hint>Type decimal lat/lon for an exact spot, or leave blank and use an option below.</div>
<div class=row><input type=checkbox id=pin checked><label for=pin style="margin:0;font-weight:400">
Pin Sally's current GPS as the location</label></div>
<div class=row><input type=checkbox id=geo><label for=geo style="margin:0;font-weight:400">
…or use my phone's location</label></div>
<div class=row><input type=checkbox id=fav><label for=fav style="margin:0;font-weight:400">
⭐ Save as a favourite place (not part of the route)</label></div>
<div class=hint>Unchecked + a findable place name = look it up online.</div>
<label>Notes (optional)</label><input id=notes placeholder="e.g. last cheap diesel">
<button id=go type=submit>Add waypoint</button>
</form><div id=out></div></main><script>
var out=document.getElementById('out'),go=document.getElementById('go');
function show(ok,msg){out.style.display='block';out.className=ok?'ok':'err';out.textContent=msg;}
function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function api(fd){return fetch('/api/waypoints',{method:'POST',body:fd});}
function load(){fetch('/api/waypoints').then(r=>r.json()).then(d=>{
 var ws=(d.waypoints||[]).slice().sort(function(a,b){return (a.order||0)-(b.order||0);});
 var el=document.getElementById('list');
 if(!ws.length){el.innerHTML='<p class=hint>No waypoints yet — add your first below.</p>';return;}
 var ic={fuel:'⛽',camp:'🏕️',scenic:'🌄',stop:'📍'};
 el.innerHTML=ws.map(function(w){
  var icon=w.favourite?'⭐':(ic[w.type]||'📍');
  var act=w.favourite
   ?'<button data-p="'+w.id+'">➕ route</button>'
   :'<button data-v="'+w.id+'" data-s="'+(w.visited?'0':'1')+'">'+(w.visited?'↺':'✓')+'</button>';
  return '<div class="wp'+(w.visited?' done':'')+'">'+
   '<span class=n>'+icon+' '+esc(w.name)+'</span>'+
   '<span class=a>'+act+'<button class=del data-d="'+w.id+'">✕</button></span></div>';}).join('');
 el.querySelectorAll('[data-d]').forEach(function(b){b.onclick=function(){
  var fd=new FormData();fd.append('op','delete');fd.append('id',b.getAttribute('data-d'));api(fd).then(load);};});
 el.querySelectorAll('[data-v]').forEach(function(b){b.onclick=function(){
  var fd=new FormData();fd.append('op','visit');fd.append('id',b.getAttribute('data-v'));
  fd.append('visited',b.getAttribute('data-s'));api(fd).then(load);};});
 el.querySelectorAll('[data-p]').forEach(function(b){b.onclick=function(){
  var fd=new FormData();fd.append('op','promote');fd.append('id',b.getAttribute('data-p'));api(fd).then(load);};});
}).catch(function(){document.getElementById('list').textContent='Could not load waypoints.';});}
load();
document.getElementById('f').onsubmit=function(e){e.preventDefault();
 var name=document.getElementById('name').value.trim();
 if(!name){show(false,'Give the waypoint a name.');return;}
 var fd=new FormData();fd.append('op','add');fd.append('name',name);
 fd.append('type',document.getElementById('type').value);
 fd.append('notes',document.getElementById('notes').value);
 var la=document.getElementById('lat').value.trim(),lo=document.getElementById('lon').value.trim();
 if(la&&lo){fd.append('lat',la);fd.append('lon',lo);}
 if(document.getElementById('fav').checked)fd.append('favourite','1');
 if(document.getElementById('pin').checked)fd.append('pin','1');
 function send(){go.disabled=true;api(fd).then(r=>r.json()).then(function(d){go.disabled=false;
   if(d.ok){show(true,'Added.');document.getElementById('name').value='';document.getElementById('notes').value='';load();}
   else show(false,'Could not add: '+(d.error||'try again'));})
   .catch(function(){go.disabled=false;show(false,'Network error — are you on SallyNet Wi-Fi?');});}
 if(document.getElementById('geo').checked&&navigator.geolocation){
  navigator.geolocation.getCurrentPosition(function(p){fd.append('lat',p.coords.latitude);
   fd.append('lon',p.coords.longitude);send();},function(){send();},{timeout:8000});
 }else send();};
</script></body></html>"""


@app.route("/api/waypoints")
def api_waypoints_get():
    """The full waypoint list (the phone editor renders it; the map reads it each render)."""
    data = _waypoints.get()
    return jsonify({"schemaVersion": cfg.SCHEMA_VERSION,
                    "waypoints": data.get("waypoints") or []})


def _write_waypoints(wlist):
    store.atomic_write_json(cfg.WAYPOINTS_JSON, {
        "schemaVersion": cfg.SCHEMA_VERSION,
        "waypoints": [_prune(w) for w in wlist],
    })
    _waypoints.invalidate()


@app.route("/api/waypoints", methods=["POST"])
def api_waypoints_post():
    """Add / delete / toggle-visited / promote / favourite a waypoint. Location for an add comes
    from an explicit lat/lon, the phone's GPS, Sally's current gpsd fix (pin=1), or geocoding the
    name. A `favourite` is a saved place (no route order); `promote` turns one into a route stop."""
    wlist = list(_waypoints.get().get("waypoints") or [])
    op = request.form.get("op", "add")

    if op == "delete":
        wid = request.form.get("id", "")
        _write_waypoints([w for w in wlist if w.get("id") != wid])
        return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": True})

    if op == "visit":
        wid = request.form.get("id", "")
        val = request.form.get("visited", "1") == "1"
        for w in wlist:
            if w.get("id") == wid:
                w["visited"] = val
                w["updatedTs"] = int(time.time())
        _write_waypoints(wlist)
        return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": True})

    if op == "promote":  # a favourite becomes a route stop (gets an order, drops the flag)
        wid = request.form.get("id", "")
        nxt_order = max([w.get("order") or 0 for w in wlist] + [0]) + 1
        for w in wlist:
            if w.get("id") == wid:
                w.pop("favourite", None)
                w["order"] = nxt_order
                w["visited"] = False
                w["updatedTs"] = int(time.time())
        _write_waypoints(wlist)
        return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": True})

    if op == "favourite":  # toggle an existing record to/from a (route-less) saved place
        wid = request.form.get("id", "")
        val = request.form.get("favourite", "1") == "1"
        for w in wlist:
            if w.get("id") == wid:
                w["favourite"] = True if val else None
                if val:
                    w["order"] = None  # leaving the route
                w["updatedTs"] = int(time.time())
        _write_waypoints(wlist)
        return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": True})

    name = request.form.get("name", "").strip()
    if not name:
        return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": False, "error": "name required"}), 400
    wtype = request.form.get("type", "stop").strip().lower()
    if wtype not in waypoints_mod.VALID_TYPES:
        wtype = "stop"
    lat, lon = _num(request.form.get("lat")), _num(request.form.get("lon"))
    if (lat is None or lon is None) and request.form.get("pin"):
        gps = _cached_fix()
        if gps["fix"] and gps["lat"] is not None:
            lat, lon = gps["lat"], gps["lon"]
    if lat is None or lon is None:
        geo = _geocode(name)
        if geo:
            lat, lon = geo
    if lat is None or lon is None:
        return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": False,
                        "error": "no location — pin GPS, allow phone location, or use a findable place name"}), 400

    # A favourite is a saved place (no route order); a normal add gets the next order.
    fav = request.form.get("favourite") in ("1", "true", "on")
    order = None if fav else max([w.get("order") or 0 for w in wlist] + [0]) + 1
    rec = {
        "id": store.slug(name) + "-" + os.urandom(2).hex(),
        "order": order, "name": name,
        "lat": round(lat, 6), "lon": round(lon, 6),
        "type": wtype, "visited": False,
        "favourite": True if fav else None,
        "arriveRadiusM": cfg.DEST_RADIUS_M,
        "notes": request.form.get("notes", "").strip() or None,
        "updatedTs": int(time.time()),
    }
    wlist.append(rec)
    _write_waypoints(wlist)
    return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": True, "id": rec["id"]})


@app.route("/waypoints")
def waypoints_page():
    """Mobile waypoint editor."""
    return Response(_WAYPOINTS_HTML, mimetype="text/html")


# Shared map view-state. A layer toggle made on /map persists here server-side, so every browser
# AND the Roku glass (which fetches /api/map.png with no layers param) render the SAME layers.
@app.route("/api/view")
def api_view_get():
    vs = _view_state()
    return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "layers": vs["layers"],
                    "baseSource": vs["baseSource"], "allLayers": sorted(_all_layers())})


@app.route("/api/view", methods=["POST"])
def api_view_post():
    """Update the shared view-state. `layers` = CSV subset of the layer set; `baseSource` =
    street|satellite (satellite reserved). Unknown names are dropped; an empty selection is
    rejected so a viewer can't blank the Roku."""
    allset = _all_layers()
    cur = _view_state()
    layers, base_source = cur["layers"], cur["baseSource"]
    if "layers" in request.form:
        want = [s.strip() for s in request.form["layers"].split(",") if s.strip() in allset]
        if not want:
            return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": False,
                            "error": "select at least one layer"}), 400
        layers = want
    bs = request.form.get("baseSource")
    if bs in ("street", "satellite"):
        base_source = bs
    store.atomic_write_json(cfg.VIEW_STATE_JSON, {
        "schemaVersion": cfg.SCHEMA_VERSION, "layers": layers,
        "baseSource": base_source, "updatedTs": int(time.time())})
    _view.invalidate()
    return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": True,
                    "layers": layers, "baseSource": base_source})


def _file_ext(name):
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _ext_allowed(ext):
    return ext in cfg.UPLOAD_VIDEO_EXT or ext in cfg.UPLOAD_PHOTO_EXT


def _sniff_ok(path, ext):
    """Light magic-byte gate on top of the extension allowlist — catches a renamed
    .txt/.html/.sh; accepts recognized image/video containers."""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        return False
    if len(head) < 4:
        return False
    if head[:3] == b"\xff\xd8\xff":            return True   # jpeg
    if head[:8] == b"\x89PNG\r\n\x1a\n":        return True   # png
    if head[:4] == b"GIF8":                     return True   # gif
    if head[:2] == b"BM":                       return True   # bmp
    if head[:4] in (b"II*\x00", b"MM\x00*"):    return True   # tiff
    if head[:4] == b"RIFF":                     return True   # webp/avi
    if head[4:8] == b"ftyp":                    return True   # mp4/mov/m4v/heic/3gp (ISO-BMFF)
    if head[:4] == b"\x1aE\xdf\xa3":            return True   # mkv/webm (EBML)
    if head[:3] == b"FLV":                      return True   # flv
    if head[:4] == b"\x30\x26\xb2\x75":         return True   # wmv/asf
    # Unknown signature: reject if it looks like plain text/script.
    if all(32 <= b < 127 or b in (9, 10, 13) for b in head):
        return False
    return True


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Guest upload — stream files verbatim into a new inbox batch (EXIF preserved)."""
    files = request.files.getlist("files") or request.files.getlist("files[]")
    if not files:
        one = request.files.get("file")
        files = [one] if one else []
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": False,
                        "error": "no files"}), 400

    batch = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S") + "--" + os.urandom(2).hex()
    bdir = os.path.join(cfg.INBOX_DIR, batch)
    os.makedirs(bdir, exist_ok=True)

    accepted, rejected = [], []
    for f in files:
        ext = _file_ext(f.filename)
        if not _ext_allowed(ext):
            rejected.append({"name": f.filename, "reason": "unsupported_type"})
            continue
        name = secure_filename(f.filename) or ("file-" + os.urandom(3).hex() + "." + ext)
        dest = os.path.join(bdir, name)
        if os.path.exists(dest):
            name = os.urandom(3).hex() + "-" + name
            dest = os.path.join(bdir, name)
        f.save(dest)  # streams to disk
        if not _sniff_ok(dest, ext):
            try:
                os.remove(dest)
            except OSError:
                pass
            rejected.append({"name": f.filename, "reason": "bad_content"})
            continue
        accepted.append({"name": f.filename, "bytes": os.path.getsize(dest)})

    if not accepted:
        try:
            os.rmdir(bdir)
        except OSError:
            pass
        return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": False,
                        "batchId": batch, "accepted": [], "rejected": rejected}), 415

    meta = {
        "uploader": request.form.get("uploader", "").strip() or None,
        "trip": request.form.get("trip", "").strip() or None,
        "tripTitle": request.form.get("tripTitle", "").strip() or None,
        "ts": int(time.time()),
    }
    lat, lon = request.form.get("lat"), request.form.get("lon")
    if lat and lon:
        try:
            meta["lat"], meta["lon"] = float(lat), float(lon)
        except ValueError:
            pass
    with open(os.path.join(bdir, "upload.json"), "w") as jf:
        json.dump(_prune(meta), jf)

    return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": True, "batchId": batch,
                    "accepted": accepted, "rejected": rejected})


@app.route("/upload")
def upload_page():
    """Mobile-first guest upload form (served to phones on SallyNet WiFi)."""
    return Response(_UPLOAD_HTML, mimetype="text/html")


@app.route("/trip")
def trip_page():
    """Driver/navigator trip-entry form."""
    return Response(_TRIP_HTML, mimetype="text/html")


@app.route("/api/trip")
def api_trip_get():
    """Current trip store — the form shows the active trip + offers to end it."""
    data = _trips.get()
    return jsonify({"schemaVersion": cfg.SCHEMA_VERSION,
                    "activeTripId": data.get("activeTripId"),
                    "trips": data.get("trips") or {}})


def _write_hdd_trip_json(rec):
    """Best-effort mirror to the media disk's trips/<cid>/trip.json so the media pipeline
    keeps its hand-editable per-collection file. The SD trips.json is canonical; an
    unmounted/full media disk just means this no-ops."""
    try:
        d = os.path.join(cfg.MEDIA_ROOT, "trips", rec["id"])
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, "trip.json.tmp")
        with open(tmp, "w") as f:
            json.dump(_prune({k: rec.get(k) for k in
                              ("id", "kind", "title", "place", "dateStart", "dateEnd")}), f)
        os.replace(tmp, os.path.join(d, "trip.json"))
    except OSError:
        pass


@app.route("/api/trip", methods=["POST"])
def api_trip_post():
    """Create/replace the active trip (or end it). Geocodes the destination over LTE,
    or pins the current GPS as a fallback, so the camping geofence has coordinates."""
    data = _trips.get()
    store_obj = {"activeTripId": data.get("activeTripId"),
                 "trips": dict(data.get("trips") or {})}

    if request.form.get("end"):
        store_obj["activeTripId"] = None
        store.atomic_write_json(cfg.TRIPS_JSON, store_obj)
        _trips.invalidate()
        return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": True, "activeTripId": None})

    title = request.form.get("title", "").strip()
    if not title:
        return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": False,
                        "error": "title required"}), 400
    cid = store.slug(title)
    if not cid:
        return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": False,
                        "error": "title has no usable characters"}), 400

    dest_name = request.form.get("destName", "").strip() or None
    aboard = [n.strip() for n in request.form.get("aboard", "").split(",") if n.strip()]

    # Destination coords: pin current GPS if asked (offline escape hatch), else geocode.
    dest = None
    dest_reason = None
    if request.form.get("pin"):
        lat, lon = request.form.get("lat"), request.form.get("lon")
        if lat and lon:
            try:
                dest = {"lat": float(lat), "lon": float(lon)}
            except ValueError:
                dest = None
        if dest is None:
            gps = read_fix(cfg.GPSD_HOST, cfg.GPSD_PORT)
            if gps["fix"] and gps["lat"] is not None:
                dest = {"lat": gps["lat"], "lon": gps["lon"]}
        if dest is None:
            dest_reason = "no GPS fix to pin"
    elif dest_name:
        geo = _geocode(dest_name)
        if geo:
            dest = {"lat": geo[0], "lon": geo[1]}
        else:
            dest_reason = "destination not found / offline"

    # Keep an existing dest if re-saving the same trip without resolving a new one.
    prior = store_obj["trips"].get(cid, {})
    if dest is None and prior.get("dest"):
        dest = prior["dest"]

    rec = {
        "id": cid,
        "kind": "trip",
        "title": title,
        "place": dest_name or prior.get("place"),
        "destName": dest_name or prior.get("destName"),
        "dest": dest,
        "aboard": aboard,
        "dateStart": request.form.get("dateStart", "").strip() or prior.get("dateStart") or None,
        "dateEnd": request.form.get("dateEnd", "").strip() or prior.get("dateEnd") or None,
        "createdTs": prior.get("createdTs") or int(time.time()),
        "updatedTs": int(time.time()),
    }
    store_obj["trips"][cid] = _prune(rec)
    store_obj["activeTripId"] = cid
    store.atomic_write_json(cfg.TRIPS_JSON, store_obj)
    _trips.invalidate()
    _write_hdd_trip_json(rec)

    return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": True, "id": cid,
                    "dest": dest, "destReason": dest_reason})


@app.route("/fuel")
def fuel_page():
    """Driver fuel/mileage entry form."""
    return Response(_FUEL_HTML, mimetype="text/html")


def _num(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _append_fuel_md(entry):
    """Mirror each fill-up into a human-readable Markdown table (best-effort)."""
    try:
        path = cfg.FUEL_LOG_MD
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        new = not os.path.exists(path)
        with open(path, "a") as f:
            if new:
                f.write("# Sally fuel log\n\n")
                f.write("| Date | Odometer (km) | Litres | $/L | Total | L/100km |\n")
                f.write("|---|---|---|---|---|---|\n")
            f.write("| %s | %s | %s | %s | %s | %s |\n" % (
                entry.get("datetime", ""), entry.get("odo_km", ""),
                entry.get("litres", ""), entry.get("price_per_l", ""),
                entry.get("total_cost", ""),
                entry.get("l_100km", "") if entry.get("l_100km") is not None else ""))
    except OSError:
        pass


@app.route("/api/fuel-log", methods=["POST"])
def api_fuel_log():
    """Log a fill-up. Computes L/100km + mpg from the odometer delta to the previous
    fill, stamps GPS time + location, appends to fuel-log.json (SD) + docs/fuel-log.md."""
    odo = _num(request.form.get("odo"))
    litres = _num(request.form.get("litres"))
    price = _num(request.form.get("price"))
    if litres is None or litres <= 0:
        return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": False,
                        "error": "litres required"}), 400

    gps = read_fix(cfg.GPSD_HOST, cfg.GPSD_PORT)
    # Prefer GPS UTC time (the Pi has no RTC and may be offline); fall back to server clock.
    when = gps.get("time") or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    data = _fuel.get()
    entries = list(data.get("entries") or [])

    entry = {
        "ts": int(time.time()),
        "datetime": when,
        "odo_km": odo,
        "litres": round(litres, 2),
        "price_per_l": price,
        "total_cost": round(litres * price, 2) if price is not None else None,
    }
    if gps["fix"] and gps["lat"] is not None:
        entry["lat"], entry["lon"] = gps["lat"], gps["lon"]

    # Economy for THIS tank = litres just added / distance since the previous fill.
    prev_odo = next((e["odo_km"] for e in reversed(entries) if e.get("odo_km") is not None), None)
    if odo is not None and prev_odo is not None and odo > prev_odo:
        dist = odo - prev_odo
        entry["l_100km"] = round(litres / dist * 100.0, 1)
        entry["mpg_imp"] = round(282.481 / entry["l_100km"], 1)  # imperial gallon

    entries.append(_prune(entry))
    store.atomic_write_json(cfg.FUEL_LOG_JSON, {"schemaVersion": cfg.SCHEMA_VERSION,
                                                "entries": entries})
    _fuel.invalidate()
    _append_fuel_md(entry)
    return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "ok": True, "entry": _prune(entry)})


@app.route("/api/state")
def api_state():
    gps = _cached_fix()
    km_from_home = None
    if gps["fix"] and gps["lat"] is not None:
        km_from_home = round(
            _haversine_km(gps["lat"], gps["lon"], cfg.HOME_LAT, cfg.HOME_LON), 1
        )

    # Active trip drives the camping geofence + the Drive-screen destination/ETA.
    active = _active_trip()
    km_to_dest = None
    trip_section = None
    if active is not None:
        dest = active.get("dest") or {}
        if gps["fix"] and gps["lat"] is not None and dest.get("lat") is not None:
            km_to_dest = round(
                _haversine_km(gps["lat"], gps["lon"], dest["lat"], dest["lon"]), 1
            )
        trip_section = _trip_state(active, km_to_dest)

    # GPS-loss alert — surfaced on every Roku screen via the existing alerts[] channel, not just
    # the map overlay. Additive; _prune drops the empty list / null nav fields.
    age, _lk, had = _fix_age_and_last(gps)
    alerts = []
    if not gps["fix"] and age is not None and age >= cfg.MAP_GPS_ALERT_AFTER_S:
        alerts.append({"kind": "gps_lost", "sev": "warn",
                       "text": "GPS signal lost", "ts": int(time.time())})

    payload = {
        "schemaVersion": cfg.SCHEMA_VERSION,
        "ts": int(time.time()),
        "mode": _derive_mode(gps, km_from_home, km_to_dest),
        "gps": gps,
        "nav": {"secondsSinceFix": age, "hadFix": had},
        "trip": trip_section,   # omitted (pruned) when no active trip
        "fuel": _fuel_state(),  # omitted (pruned) when no fill-ups logged
        "drive": {
            "odo_km": None,
            "trip_km": None,
            "km_from_home": km_from_home,
            "reverse": False,
        },
        "power": None,    # P2 — MQTT collector
        "tanks": None,    # P2
        "env": None,      # P2
        "level": None,    # P2
        "cameras": None,  # P3 — go2rtc /api/discovery
        "audio": None,    # P4
        "alerts": alerts,
        "system": {
            "host": cfg.HOSTNAME,
            "uptime_s": int(time.time() - _BOOT),
            "throttled": _throttled(),
        },
    }
    return jsonify(_prune(payload))


@app.route("/api/discovery")
def api_discovery():
    # Phase 3 fills `streams` from go2rtc on the N100. Empty for now.
    return jsonify({"schemaVersion": 1, "host": cfg.HOSTNAME, "streams": {}})


@app.route("/api/health")
def api_health():
    gps = read_fix(cfg.GPSD_HOST, cfg.GPSD_PORT, window=1.5)
    return jsonify({"ok": True, "gps_fix": gps["fix"], "ts": int(time.time())})


@app.route("/")
def index():
    return jsonify({
        "service": "sally-api",
        "schemaVersion": cfg.SCHEMA_VERSION,
        "endpoints": [
            "/api/state", "/api/discovery", "/api/health",
            "/api/media?type=trips", "/api/collections/<id>", "/api/photos",
            "/media/<path>", "/api/qr.png", "/api/map.png", "/map", "/api/view", "/api/upload",
            "/upload", "/trip", "/api/trip", "/api/waypoints", "/waypoints", "/fuel", "/api/fuel-log",
        ],
    })


if __name__ == "__main__":
    # Guest uploads can be large and concurrent; the single-threaded dev server can't
    # cope. Prefer waitress when present, else at least enable threading.
    try:
        from waitress import serve
        serve(app, host=cfg.HOST, port=cfg.PORT, threads=8)
    except ImportError:
        app.run(host=cfg.HOST, port=cfg.PORT, threaded=True)
