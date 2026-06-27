#!/usr/bin/env python3
# SallyNet LTE modem monitor — runs ON campingpi as a long-lived service
# (sally-lte-monitor.service). Polls the QX210-NW2 router's LuCI HTTP API for the
# cellular WAN (wwan0) byte counters + modem signal, and publishes to the local
# mosquitto broker for Home Assistant / Grafana.
#
# Why HTTP and not SSH/SNMP: the QX210 exposes ONLY LuCI on :80 (dropbear is
# disabled), and the modem signal (dBm/CSQ/operator/network) lives in the LuCI
# overview JSON, not in any SNMP MIB. So one authenticated HTTP poller covers
# both bandwidth and signal with zero router-side changes. See
# subsystems/network/lte-monitoring.md and CLAUDE.md (QX210 mgmt = LuCI only).
#
# Stdlib only (Pi is on EOL Buster, Python 3.7, no paho) — publishes by shelling
# out to mosquitto_pub. Config comes from the environment (systemd
# EnvironmentFile=/etc/sally/lte-monitor.env).
import http.cookiejar
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# --- config (env, with SallyNet defaults) -----------------------------------
HOST       = os.environ.get("QX210_HOST", "192.168.2.1")
LUCI_USER  = os.environ.get("QX210_LUCI_USER", "admin")
LUCI_PASS  = os.environ.get("QX210_LUCI_PASS", "")
IFACE      = os.environ.get("LTE_IFACE", "wwan0")
MQTT_HOST  = os.environ.get("MQTT_HOST", "127.0.0.1")
MQTT_PORT  = os.environ.get("MQTT_PORT", "1883")
PREFIX     = os.environ.get("MQTT_PREFIX", "sally/telemetry/lte")
INTERVAL   = max(2, int(os.environ.get("INTERVAL", "10")))
HA_DISC    = os.environ.get("HA_DISCOVERY", "1") not in ("0", "", "false", "no")
HA_PREFIX  = os.environ.get("HA_PREFIX", "homeassistant")

BASE        = "http://%s/cgi-bin/luci" % HOST
STATE_TOPIC = PREFIX + "/state"
STAT_TOPIC  = PREFIX + "/status"          # online / offline (availability)
EXPIRE      = INTERVAL * 3                 # HA marks sensors unavailable after this

def log(msg):
    # systemd journal captures stdout; flush so lines are not buffered away.
    print("%s lte-monitor: %s" % (time.strftime("%H:%M:%S"), msg), flush=True)

# --- LuCI session -----------------------------------------------------------
_cj = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))

def login():
    data = urllib.parse.urlencode(
        {"luci_username": LUCI_USER, "luci_password": LUCI_PASS}).encode()
    _opener.open(urllib.request.Request(BASE + "/", data=data), timeout=15).read()
    if not any(c.name.startswith("sysauth") for c in _cj):
        raise RuntimeError("login did not yield a sysauth cookie (bad password?)")

def _get(path):
    return _opener.open(BASE + path, timeout=20).read()

def get_json(path):
    """GET a LuCI JSON endpoint, re-logging-in once if the session has lapsed
    (LuCI then returns the HTML login page instead of JSON)."""
    for attempt in (1, 2):
        try:
            return json.loads(_get(path))
        except (ValueError, urllib.error.HTTPError) as e:
            if attempt == 2:
                raise
            log("session stale (%s) — re-authenticating" % type(e).__name__)
            login()

# --- sampling ---------------------------------------------------------------
def rates():
    """wwan0 byte rates from the LuCI realtime series: [t, rxB, rxP, txB, txP].
    rx = download, tx = uplink. Smooths over the last few samples and ignores a
    counter wrap/reset (32-bit counters wrap ~every 4 GB on this router)."""
    series = get_json("/admin/status/realtime/bandwidth_status/" + IFACE)
    pts = [p for p in series if isinstance(p, list) and len(p) >= 5]
    if len(pts) < 2:
        return None
    win = pts[-4:] if len(pts) >= 4 else pts
    t0, rx0, _, tx0, _ = win[0][:5]
    t1, rx1, _, tx1, _ = win[-1][:5]
    dt = t1 - t0
    drx, dtx = rx1 - rx0, tx1 - tx0
    if dt <= 0 or drx < 0 or dtx < 0:        # wrap / reset within the window
        return {"rx_bytes_total": rx1, "tx_bytes_total": tx1}
    return {
        "down_bps": int(drx * 8 / dt), "up_bps": int(dtx * 8 / dt),
        "down_kbps": round(drx * 8 / dt / 1000, 1),
        "up_kbps": round(dtx * 8 / dt / 1000, 1),
        "rx_bytes_total": rx1, "tx_bytes_total": tx1,
    }

def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None

def modem_signal():
    """Modem signal from the LuCI overview JSON (wan34g_modem[0])."""
    d = get_json("/admin/status/overview?status=1")
    arr = d.get("wan34g_modem") or []
    out = {"router_uptime": d.get("uptime")}
    if not arr:
        return out
    m = arr[0]
    csq = _int(m.get("rssi"))                # 0..31 (99 = unknown)
    out.update({
        "signal_dbm": _int(m.get("dbm")),
        "rssi_csq": csq,
        "rssi_pct": round(csq / 31 * 100) if csq is not None and csq != 99 else None,
        "operator": m.get("opera"),
        "network": m.get("stand"),           # e.g. "FDD LTE"
        "conn_status": m.get("status"),      # e.g. "connected"
        "sim_status": m.get("sim_status"),
        "sim_slot": m.get("sim_slot"),
        "modem_model": m.get("model"),
        "modem_manuf": m.get("manuf"),
    })
    return out

# --- MQTT (via mosquitto_pub) -----------------------------------------------
def mpub(topic, payload, retain=False):
    cmd = ["mosquitto_pub", "-h", MQTT_HOST, "-p", MQTT_PORT,
           "-t", topic, "-m", payload]
    if retain:
        cmd.append("-r")
    try:
        subprocess.run(cmd, check=True, timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log("mqtt publish to %s failed: %s" % (topic, e))

def publish_discovery():
    """Home Assistant MQTT discovery — one device, several sensors that read the
    shared JSON state topic. Republished retained at startup."""
    dev = {"identifiers": ["sally_lte"], "name": "Sally LTE Modem",
           "manufacturer": "MEIG", "model": "SLM750-V (QX210)", "via_device": "sally"}
    sensors = [
        ("uplink",   "Sally LTE Uplink",   "up_kbps",     "kbit/s", None, "mdi:upload-network",   None),
        ("downlink", "Sally LTE Downlink", "down_kbps",   "kbit/s", None, "mdi:download-network", None),
        ("signal",   "Sally LTE Signal",   "signal_dbm",  "dBm", "signal_strength", None, None),
        ("rssi",     "Sally LTE RSSI",     "rssi_pct",    "%", None, "mdi:signal", None),
        ("operator", "Sally LTE Operator", "operator",    None, None, "mdi:domain", None),
        ("network",  "Sally LTE Network",  "network",     None, None, "mdi:radio-tower", None),
        ("conn",     "Sally LTE Status",   "conn_status", None, None, "mdi:lan-connect", None),
        ("tx_total", "Sally LTE Uploaded",   "tx_bytes_total", "MB", "data_size", None, "total_increasing"),
        ("rx_total", "Sally LTE Downloaded", "rx_bytes_total", "MB", "data_size", None, "total_increasing"),
    ]
    for obj, name, field, unit, dclass, icon, sclass in sensors:
        if field.endswith("_bytes_total"):
            tmpl = "{{ (value_json.%s | float / 1048576) | round(1) }}" % field
        else:
            tmpl = "{{ value_json.%s }}" % field
        cfg = {
            "name": name, "unique_id": "sally_lte_" + obj,
            "state_topic": STATE_TOPIC, "value_template": tmpl,
            "availability_topic": STAT_TOPIC,
            "payload_available": "online", "payload_not_available": "offline",
            "expire_after": EXPIRE, "device": dev,
        }
        if unit:   cfg["unit_of_measurement"] = unit
        if dclass: cfg["device_class"] = dclass
        if icon:   cfg["icon"] = icon
        if sclass: cfg["state_class"] = sclass
        mpub("%s/sensor/sally_lte_%s/config" % (HA_PREFIX, obj),
             json.dumps(cfg), retain=True)
    log("published HA discovery for %d sensors" % len(sensors))

# --- main loop --------------------------------------------------------------
_running = True
def _stop(*_):
    global _running
    _running = False

def main():
    if not LUCI_PASS:
        log("FATAL: QX210_LUCI_PASS is empty — set it in /etc/sally/lte-monitor.env")
        sys.exit(1)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    login()
    log("logged in to %s; polling %s every %ds -> %s" % (HOST, IFACE, INTERVAL, STATE_TOPIC))
    mpub(STAT_TOPIC, "online", retain=True)
    if HA_DISC:
        publish_discovery()

    while _running:
        t0 = time.time()
        try:
            rec = {"ts": int(t0), "iface": IFACE}
            r = rates()
            if r:
                rec.update(r)
            rec.update(modem_signal())
            mpub(STATE_TOPIC, json.dumps(rec), retain=True)
            mpub(STAT_TOPIC, "online", retain=True)
            if "up_bps" in rec:
                log("up=%.1f down=%.1f kbps  %s dBm  %s %s"
                    % (rec.get("up_kbps", 0), rec.get("down_kbps", 0),
                       rec.get("signal_dbm"), rec.get("operator"), rec.get("network")))
        except Exception as e:                # keep the service alive across blips
            log("poll error: %s: %s" % (type(e).__name__, e))
        # sleep the remainder of the interval, but stay responsive to SIGTERM
        while _running and time.time() - t0 < INTERVAL:
            time.sleep(0.5)

    mpub(STAT_TOPIC, "offline", retain=True)
    log("stopped")

if __name__ == "__main__":
    main()
