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
