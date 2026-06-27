# QX210-NW2 router — LuCI management + serial port

Deep reference for driving the cellular router. Authoritative docs:
`subsystems/network/README.md` and `subsystems/network/lte-monitoring.md`.

## LuCI is the only management surface

**SSH/dropbear is disabled** on the QX210 (verified 2026-06-26) — only LuCI on HTTP
`:80` answers. Any automation must speak HTTP to LuCI, not ssh. Reach it at
`http://192.168.2.1` (LAN) or `http://10.66.12.1` (over the tunnel). UCI config of
interest: `/etc/config/network` (WAN profiles: cell vs WiFi-as-WAN) and
`/etc/config/wireless` (SSID + repeater).

## Authenticated session (HTTP POST login)

LuCI uses a `sysauth` cookie. Log in by POSTing credentials, then reuse the cookie:

```python
import urllib.parse, urllib.request
data = urllib.parse.urlencode(
    {"luci_username": LUCI_USER, "luci_password": LUCI_PASS}).encode()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
opener.open(urllib.request.Request(BASE + "/", data=data), timeout=15).read()
# subsequent opener.open(...) calls carry the sysauth cookie
```

Credentials come from the repo `.env`: `QX210_LUCI_USER` (`admin`), `QX210_LUCI_PASS`.
Host vars: `QX210_HOST` (`192.168.2.1`), `QX210_HOST_VPN` (`10.66.12.1`),
`QX210_WAN_CELL_IFACE` (`wwan0`).

## JSON endpoints

| Endpoint (under `/cgi-bin/luci`) | Returns |
|---|---|
| `/admin/status/realtime/bandwidth_status/wwan0` | array `[epoch, rxBytes, rxPkts, txBytes, txPkts]` — LTE byte counters (tx = uplink) |
| `/admin/status/overview?status=1` | modem block `wan34g_modem[0]`: `dbm`, `rssi` (CSQ), `opera`, `stand`, `status`, `sim_status`, `model` |

`scripts/lte-monitor.py` is the worked reference — stdlib-only (Pi is on EOL Buster,
Python 3.7, no `paho`), publishes via `mosquitto_pub` subprocess, handles cookie
re-auth and 32-bit counter wrap (~every 4 GB on this router).

## RS232 port is a DTU, not a console

The QX210's RS232 port is a **data DTU** (Modbus RTU↔TCP gateway / raw TCP-UDP
passthrough) — **do not try to get a router shell on it**. The Pi's PL011 UART
(`/dev/serial0`, freed by disabling BT) is the side that wires to it.

**Before wiring, meter the router's TX/B→GND at idle** (it can be 3.3 V TTL, true
±RS-232, or RS-485 — the wrong one fries GPIO15):

| Reading | Meaning | Action |
|---|---|---|
| ≈ +3.3 V | 3.3 V TTL UART | wire directly to Pi RXD0/TXD0 |
| ≈ −5…−12 V | true RS-232 | needs a MAX3232 level shifter |
| ≈ 0 / floating / ~2.5 V | likely RS-485 | set RS-232 in UCI, or use an RS-485 transceiver |

Pi side is already prepared: `enable_uart=1` + `dtoverlay=disable-bt` in
`/boot/config.txt`, serial console stripped from `/boot/cmdline.txt`. Full pinout +
gate: `subsystems/network/router-serial-uart.md`.

## Cell RF

Roof-mount directional antenna → **ANNTLENT** Band 2/5/12/17 indoor booster → modem.
The booster is electrically separate from the router; it lifts RF before the modem.
