"""sally-api configuration.

All values overridable via environment so the same code runs on the Pi now and the
N100 later without edits.
"""
import os

SCHEMA_VERSION = 1

HOST = os.environ.get("SALLY_API_HOST", "0.0.0.0")
PORT = int(os.environ.get("SALLY_API_PORT", "8090"))

# gpsd endpoint (local on the brains host).
GPSD_HOST = os.environ.get("GPSD_HOST", "127.0.0.1")
GPSD_PORT = int(os.environ.get("GPSD_PORT", "2947"))

# Home-base anchor — default = the owner's Edmonton home. Drives "km from home",
# the AT_HOME mode, and (later) default map centering. 1 km radius keeps the whole
# home neighbourhood as "home" (parking spot, street, nearby errands).
HOME_LAT = float(os.environ.get("SALLY_HOME_LAT", "53.5461"))
HOME_LON = float(os.environ.get("SALLY_HOME_LON", "-113.4938"))
HOME_RADIUS_M = float(os.environ.get("SALLY_HOME_RADIUS_M", "1000"))

# Instantaneous mode hint threshold (the Roku applies the real hysteresis).
DRIVING_KMH = float(os.environ.get("SALLY_DRIVING_KMH", "10.0"))

# CAMPING geofence: when an active trip has destination coords and we're stopped
# within this radius of them, the mode is "camping" (vs. a generic "parked").
DEST_RADIUS_M = float(os.environ.get("SALLY_DEST_RADIUS_M", "250"))

# Host label surfaced on the Systems screen.
HOSTNAME = os.environ.get("SALLY_HOSTNAME", "campingpi")

# --- home-media (P1/P5) ------------------------------------------------------
# Served library root: GET /media/<path> maps here. Sidecars + catalog.json are the
# read-model rebuilt by scripts/media-reindex.py. INBOX is where guest uploads land for
# the ingest worker. All env-overridable so Pi -> N100 is a path change.
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", "/mnt/usb/home/library")
CATALOG_JSON = os.environ.get("CATALOG_JSON", "/var/lib/sally/catalog.json")
INBOX_DIR = os.environ.get("INBOX_DIR", "/mnt/usb/home/inbox")

# --- studio library: Movies / TV (Workstream A) ------------------------------
# Personally-owned library, a sibling of home/ on the same disk (confirmed live:
# STUDIO_ROOT/movies/<Title (Year)>/..., STUDIO_ROOT/tv/<Show>/Season N/...) — kept
# separate from MEDIA_ROOT so broadening it can never change how existing Trips URLs
# resolve (see _safe_media_path's dispatch in app.py).
STUDIO_ROOT = os.environ.get("STUDIO_ROOT", "/mnt/usb")
MOVIES_JSON = os.environ.get("MOVIES_JSON", "/var/lib/sally/movies.json")
TV_JSON = os.environ.get("TV_JSON", "/var/lib/sally/tv.json")

# TMDB artwork + genre enrichment (studio_art.py). Creds come from .env.tmdb, delivered
# into /opt/sally/sally-api.env by scripts/deploy-sally-api.sh — the exact TILE_API_KEY
# pattern; nothing is committed. v3 api_key query-param auth (the read token is kept as an
# escape hatch, unused by v3). With no key the enrichment degrades to frame-grab posters +
# a Recently Added / All Movies catalog, fully offline. Posters + the index cache under
# STUDIO_ROOT/.art so /media/.art/<id>.jpg serves them; studio-overrides.json is the
# git-tracked hand-correction file (genres/kidSafe/poster + match fixes).
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
TMDB_API_READ_TOKEN = os.environ.get("TMDB_API_READ_ACCESS_TOKEN", "")
TMDB_API_BASE = os.environ.get("TMDB_API_BASE", "https://api.themoviedb.org/3")
TMDB_IMAGE_BASE = os.environ.get("TMDB_IMAGE_BASE", "https://image.tmdb.org/t/p")
TMDB_POSTER_SIZE = os.environ.get("TMDB_POSTER_SIZE", "w342")
STUDIO_ART_DIR = os.environ.get("STUDIO_ART_DIR", os.path.join(STUDIO_ROOT, ".art"))
STUDIO_ART_INDEX = os.environ.get("STUDIO_ART_INDEX", os.path.join(STUDIO_ART_DIR, "index.json"))
STUDIO_OVERRIDES = os.environ.get("STUDIO_OVERRIDES", "/opt/sally/media/studio-overrides.json")

# --- trip + fuel logs (C2 / C3) ----------------------------------------------
# Canonical read-models on the Pi's LOCAL disk (SD), NOT the media disk — these need
# crash-safe atomic writes, and small wear-sensitive state belongs on the SD. trips.json
# is the source of truth for the dashboard's active trip AND the media pipeline's collection
# metadata (media-reindex.py prefers it over the media disk's trips/<cid>/trip.json). route.json is the
# OSRM ETA cache written by scripts/trip-eta-refresh.py. fuel-log.json is the structured
# fill-up history; docs/fuel-log.md is the human-readable mirror.
TRIPS_JSON = os.environ.get("TRIPS_JSON", "/var/lib/sally/trips.json")
ROUTE_JSON = os.environ.get("ROUTE_JSON", "/var/lib/sally/route.json")
FUEL_LOG_JSON = os.environ.get("FUEL_LOG_JSON", "/var/lib/sally/fuel-log.json")
FUEL_LOG_MD = os.environ.get("FUEL_LOG_MD", "/opt/sally/sally-api/docs/fuel-log.md")

# Geocoding + routing endpoints (used over LTE, best-effort, results cached).
# Defaults are the public OSM demo servers — fine for Sally's tiny volume; swap to a
# self-hosted instance (e.g. on the N100) via env if the demo's rate limits bite.
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org/route/v1/driving")
# A descriptive UA is required by the Nominatim usage policy.
GEO_USER_AGENT = os.environ.get("GEO_USER_AGENT", "sally-api/1.0 (sallynet motorhome dashboard)")
# ETA from route.json older than this many seconds is reported as stale to the Roku.
ROUTE_STALE_S = int(os.environ.get("ROUTE_STALE_S", "600"))

# Guest upload form + QR. LAN_BASE_URL is what the QR encodes (guests scan it on
# SallyNet WiFi); keep it the LAN IP — mDNS .local is flaky on Android and guests may be
# on cellular. UPLOAD_MAX_BYTES caps a single request (phone video is large).
LAN_BASE_URL = os.environ.get("LAN_BASE_URL", "http://192.168.2.216:8090")
UPLOAD_MAX_BYTES = int(os.environ.get("UPLOAD_MAX_BYTES", str(8 * 1024 * 1024 * 1024)))
UPLOAD_VIDEO_EXT = set("mp4 mov m4v mkv avi 3gp 3g2 webm mts m2ts wmv flv".split())
UPLOAD_PHOTO_EXT = set("jpg jpeg png heic heif webp tif tiff bmp gif".split())

# --- ambient map / navigation (P2 — subsystems/gps/map-navigation-brainstorm.md) ------
# The compositor (mapgen.py) bakes one flat PNG served at /api/map.png; the Roku just shows
# it. Basemap tiles come from a raster provider (Thunderforest Outdoors by default — the OSM
# public tile server forbids the caching/pre-seed this design needs). NOTE: Thunderforest's FREE
# Hobby tier also forbids server-side caching/pre-seed (Small Business+ or a custom plan is
# required) — the cache-forever design assumes that paid/custom arrangement; the tiles.py
# breaker/negative-cache keeps rates polite meanwhile. Put
# the key in TILE_API_KEY via the systemd unit / env; the template is .format()ed with
# z/x/y/key. With no key the basemap degrades to gap-fill and only the LOCAL layers (Sally's
# arrow, breadcrumb trail, waypoints, POI) draw — so the screen still works offline.
TILE_URL_TEMPLATE = os.environ.get(
    "TILE_URL_TEMPLATE",
    "https://tile.thunderforest.com/outdoors/{z}/{x}/{y}.png?apikey={key}")
TILE_API_KEY = os.environ.get("TILE_API_KEY", "")
# Tile cache lives on the media disk (bulky + disposable; the wrong profile for the
# wear-sensitive SD). Every tile read/write is best-effort, so a disk I/O error (unmount,
# full disk, transient fault) just becomes a cache miss -> live re-fetch and never crashes a render.
TILE_CACHE_DIR = os.environ.get("TILE_CACHE_DIR", "/mnt/usb/home/maptiles")
TILE_ATTRIBUTION = os.environ.get(
    "TILE_ATTRIBUTION", "(C) OpenStreetMap contributors  (C) Thunderforest")

# GPS breadcrumb tracks (daily YYYY-MM-DD.gpx written by scripts/media-track-logger.py).
# MUST match that script's DEPLOYED TRACKS_DIR or today's trail silently renders empty.
TRACKS_DIR = os.environ.get("TRACKS_DIR", "/var/lib/sally/tracks")

# Canonical trip waypoints (phone-edited at /waypoints, re-read each render) + the POI
# snapshot cache (scripts/poi-refresh.py from Overpass). SD + atomic, like the other stores.
WAYPOINTS_JSON = os.environ.get("WAYPOINTS_JSON", "/var/lib/sally/waypoints.json")
# Road-km/ETA to the next waypoint (OSRM), written by scripts/waypoint-eta-refresh.py — same
# shape as route.json. The map prefers this over straight-line km when it's fresh.
WAYPOINT_ROUTE_JSON = os.environ.get("WAYPOINT_ROUTE_JSON", "/var/lib/sally/waypoint-route.json")
POI_CACHE_JSON = os.environ.get("POI_CACHE_JSON", "/var/lib/sally/poi-cache.json")
OVERPASS_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")

# Shared, persisted map view-state (layer visibility + a reserved base-source selector). Written
# by POST /api/view, read by /api/map.png so every browser AND the Roku glass render identically.
VIEW_STATE_JSON = os.environ.get("VIEW_STATE_JSON", "/var/lib/sally/view-state.json")

# Background nav-tick (scripts/nav-tick.py, a Type=simple daemon reading gpsd ~every 7 s): GPS
# liveness + frozen last-known position written to nav-state.json, the source of truth for the
# /api/map.png GPS-loss overlay's fix-age. The API treats a nav-state older than NAV_STATE_STALE_S
# as absent and falls back to its own in-process fix tracker. The tick's own cadence/write-gate/
# pre-warm knobs (NAV_TICK_INTERVAL_S, NAV_HEALTHY_WRITE_S, NAV_MOVE_WRITE_M, NAV_PREWARM) are read
# by the script from env (like the other workers).
NAV_STATE_JSON = os.environ.get("NAV_STATE_JSON", "/var/lib/sally/nav-state.json")
NAV_STATE_STALE_S = float(os.environ.get("NAV_STATE_STALE_S", "30"))

# Past-trip geotagged photos surfaced as map pins (the "photos" layer). photo-poi.json is rebuilt
# by media-reindex.py (piggybacked on the catalog rebuild). PHOTO_POI_MAX_KM is a hard great-circle
# cull so a far-away trip's photo never bleeds onto the map at low zoom.
PHOTO_POI_JSON = os.environ.get("PHOTO_POI_JSON", "/var/lib/sally/photo-poi.json")
PHOTO_POI_MAX_KM = float(os.environ.get("SALLY_PHOTO_POI_MAX_KM", "40"))

# Render settings. The font + any sprites live beside the code (a minimal Buster may lack
# system fonts, so mapgen loads the .ttf by ABSOLUTE path). 1080p native; drop to 1280x720
# (the Roku Poster upscales) via env if the Pi runs hot. The two cache windows stop the Pi
# re-rendering identical frames for every Roku poll: a render is reused for MIN_RENDER_INTERVAL
# while moving, and up to PARKED_TTL while parked (center/zoom/layers unchanged).
_HERE = os.path.dirname(os.path.abspath(__file__))
MAP_SPRITE_DIR = os.environ.get("MAP_SPRITE_DIR", os.path.join(_HERE, "mapassets"))
MAP_FONT_PATH = os.environ.get("MAP_FONT_PATH", os.path.join(MAP_SPRITE_DIR, "DejaVuSans.ttf"))
MAP_W = int(os.environ.get("MAP_W", "1920"))
MAP_H = int(os.environ.get("MAP_H", "1080"))
MAP_MIN_RENDER_INTERVAL_S = float(os.environ.get("MAP_MIN_RENDER_INTERVAL_S", "3"))
MAP_PARKED_TTL_S = float(os.environ.get("MAP_PARKED_TTL_S", "20"))
# GPS-loss safety overlay: bake a banner onto /api/map.png once a fix has been missing this long.
MAP_GPS_ALERT_AFTER_S = float(os.environ.get("SALLY_GPS_ALERT_AFTER_S", "20"))

# Tile-fetch hardening (keep request rates under control with a slow/throttling provider).
# A failed tile is "cooled" (negative cache) so the next render skips straight to gap-fill
# instead of re-hitting it; the GLOBAL breaker trips after a burst of failures (or a 429) and
# serves cache-only for a cooldown so a tarpitting provider is left to recover; a single probe
# after the cooldown re-closes it. All env-tunable. (See subsystems/gps/map-tile-hardening.md.)
TILE_TIMEOUT_S = float(os.environ.get("TILE_TIMEOUT_S", "4"))            # per-tile HTTP timeout
TILE_FAIL_COOLDOWN_S = float(os.environ.get("TILE_FAIL_COOLDOWN_S", "60"))  # negative-cache TTL
TILE_BREAKER_FAILS = int(os.environ.get("TILE_BREAKER_FAILS", "6"))     # fails in window -> trip
TILE_BREAKER_WINDOW_S = float(os.environ.get("TILE_BREAKER_WINDOW_S", "20"))
TILE_BREAKER_COOLDOWN_S = float(os.environ.get("TILE_BREAKER_COOLDOWN_S", "45"))
TILE_FETCH_WORKERS = int(os.environ.get("TILE_FETCH_WORKERS", "8"))     # concurrent tile fetches
