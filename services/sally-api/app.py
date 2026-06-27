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
import time
import urllib.parse
import urllib.request
from datetime import datetime

from flask import Flask, Response, abort, jsonify, request, send_file
from werkzeug.utils import secure_filename

import sallyconf as cfg
import store
from gpsd_client import read_fix

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
_trips = store.CachedJson(cfg.TRIPS_JSON, {"activeTripId": None, "trips": {}})
_route = store.CachedJson(cfg.ROUTE_JSON, {})
_fuel = store.CachedJson(cfg.FUEL_LOG_JSON, {"entries": []})


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
    """type=trips -> home collections. movies|tv|kids (studio library) not in this build."""
    t = request.args.get("type", "trips")
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


def _safe_media_path(relpath):
    """Resolve relpath under MEDIA_ROOT, rejecting traversal."""
    root = os.path.realpath(cfg.MEDIA_ROOT)
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

    def stream(path=full, start=start, length=length, chunk=262144):
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
    """Best-effort mirror to the legacy HDD trips/<cid>/trip.json so the media pipeline
    keeps its hand-editable per-collection file. The SD trips.json is canonical; a dead
    HDD just means this no-ops."""
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
    gps = read_fix(cfg.GPSD_HOST, cfg.GPSD_PORT)
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

    payload = {
        "schemaVersion": cfg.SCHEMA_VERSION,
        "ts": int(time.time()),
        "mode": _derive_mode(gps, km_from_home, km_to_dest),
        "gps": gps,
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
        "alerts": [],
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
            "/media/<path>", "/api/qr.png", "/api/upload", "/upload",
            "/trip", "/api/trip", "/fuel", "/api/fuel-log",
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
