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

# --- trip + fuel logs (C2 / C3) ----------------------------------------------
# Canonical read-models on the Pi's LOCAL disk (SD), NOT the exFAT HDD — the HDD has
# a failing band, and these need crash-safe atomic writes. trips.json is the source of
# truth for the dashboard's active trip AND the media pipeline's collection metadata
# (media-reindex.py prefers it over the HDD trips/<cid>/trip.json). route.json is the
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
