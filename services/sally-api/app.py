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
from datetime import datetime

from flask import Flask, Response, abort, jsonify, request, send_file
from werkzeug.utils import secure_filename

import sallyconf as cfg
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


def _derive_mode(gps, km_from_home):
    if not gps["fix"]:
        return "unknown"
    if (gps["speed_kmh"] or 0) >= cfg.DRIVING_KMH:
        return "driving"
    if km_from_home is not None and km_from_home * 1000.0 <= cfg.HOME_RADIUS_M:
        return "at_home"
    return "parked"


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


@app.route("/api/media")
def api_media():
    """type=trips -> home collections. movies|tv|kids (studio library) not in this build."""
    t = request.args.get("type", "trips")
    cat = _load_catalog()
    cols = cat.get("collections", []) if t == "trips" else []
    return jsonify({"schemaVersion": cfg.SCHEMA_VERSION, "type": t, "collections": cols})


@app.route("/api/collections/<cid>")
def api_collection(cid):
    cat = _load_catalog()
    items = cat.get("items", {}).get(cid)
    if items is None:
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


@app.route("/api/state")
def api_state():
    gps = read_fix(cfg.GPSD_HOST, cfg.GPSD_PORT)
    km_from_home = None
    if gps["fix"] and gps["lat"] is not None:
        km_from_home = round(
            _haversine_km(gps["lat"], gps["lon"], cfg.HOME_LAT, cfg.HOME_LON), 1
        )
    payload = {
        "schemaVersion": cfg.SCHEMA_VERSION,
        "ts": int(time.time()),
        "mode": _derive_mode(gps, km_from_home),
        "gps": gps,
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
