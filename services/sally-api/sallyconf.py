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
# the AT_HOME mode, and (later) default map centering.
HOME_LAT = float(os.environ.get("SALLY_HOME_LAT", "53.5461"))
HOME_LON = float(os.environ.get("SALLY_HOME_LON", "-113.4938"))
HOME_RADIUS_M = float(os.environ.get("SALLY_HOME_RADIUS_M", "150"))

# Instantaneous mode hint threshold (the Roku applies the real hysteresis).
DRIVING_KMH = float(os.environ.get("SALLY_DRIVING_KMH", "8.0"))

# Host label surfaced on the Systems screen.
HOSTNAME = os.environ.get("SALLY_HOSTNAME", "campingpi")

# --- home-media (P1/P5) ------------------------------------------------------
# Served library root: GET /media/<path> maps here. Sidecars + catalog.json are the
# read-model rebuilt by scripts/media-reindex.py. INBOX is where guest uploads land for
# the ingest worker. All env-overridable so Pi -> N100 is a path change.
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", "/mnt/usb/home/library")
CATALOG_JSON = os.environ.get("CATALOG_JSON", "/var/lib/sally/catalog.json")
INBOX_DIR = os.environ.get("INBOX_DIR", "/mnt/usb/home/inbox")

# Guest upload form + QR. LAN_BASE_URL is what the QR encodes (guests scan it on
# SallyNet WiFi); keep it the LAN IP — mDNS .local is flaky on Android and guests may be
# on cellular. UPLOAD_MAX_BYTES caps a single request (phone video is large).
LAN_BASE_URL = os.environ.get("LAN_BASE_URL", "http://192.168.2.216:8090")
UPLOAD_MAX_BYTES = int(os.environ.get("UPLOAD_MAX_BYTES", str(8 * 1024 * 1024 * 1024)))
UPLOAD_VIDEO_EXT = set("mp4 mov m4v mkv avi 3gp 3g2 webm mts m2ts wmv flv".split())
UPLOAD_PHOTO_EXT = set("jpg jpeg png heic heif webp tif tiff bmp gif".split())
