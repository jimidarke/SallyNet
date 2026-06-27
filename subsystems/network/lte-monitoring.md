# LTE Modem Monitoring — wwan0 bandwidth + signal → MQTT

Live monitoring of the QX210-NW2's cellular uplink: per-second-ish **uplink/downlink
bandwidth**, cumulative byte totals, and **modem signal** (dBm, CSQ, operator,
network type, connection/SIM status). Runs on `campingpi`, publishes to the local
mosquitto broker, auto-discovered by Home Assistant.

## Why HTTP polling (not SSH counters or SNMP)

The QX210 exposes **only LuCI on :80** — SSH/dropbear is disabled and SNMP isn't
present (see [`../../CLAUDE.md`] note and memory `project_qx210_mgmt_luci_only`).
Crucially, the **modem signal lives in the LuCI overview JSON, not in any SNMP
MIB**, so even with SNMP enabled you'd still need the HTTP path for signal. One
authenticated HTTP poller therefore covers *both* bandwidth and signal with **zero
router-side changes**.

Two LuCI endpoints, polled every `INTERVAL` (default 10 s) by reusing one logged-in
session:

| Data | Endpoint | Shape |
|---|---|---|
| Byte counters | `/cgi-bin/luci/admin/status/realtime/bandwidth_status/wwan0` | series of `[epoch, rxBytes, rxPkts, txBytes, txPkts]` (rx=down, tx=up) |
| Modem signal | `/cgi-bin/luci/admin/status/overview?status=1` | JSON; `wan34g_modem[0]` → `dbm`, `rssi` (CSQ), `opera`, `stand`, `status`, `sim_status`, `model`, … |

**Signal ceiling:** this modem (MEIG SLM750-V) reports **dBm + CSQ (0–31)**, not
RSRP/RSRQ/SINR — that's the firmware's limit, but dBm is the actionable number
(observed −75 dBm = strong). Rates are smoothed over the last few samples and a
32-bit **counter wrap** (≈ every 4 GB on this router) is detected and skipped.

## Components

| File (repo) | Deployed to | Role |
|---|---|---|
| `scripts/lte-monitor.py` | `/opt/sally/net/lte-monitor.py` | the poller (stdlib only; publishes via `mosquitto_pub` — Pi has no paho) |
| `configs/network/sally-lte-monitor.service` | `/etc/systemd/system/` | `Type=simple`, `Restart=always` long-lived daemon |
| `configs/network/sally-lte-monitor.env.example` | `/etc/sally/lte-monitor.env` (0600) | config + LuCI password (rendered from repo `.env`) |
| `scripts/deploy-lte-monitor.sh` | — | key-based deploy over the WG tunnel, single-connection base64 path |

## MQTT

Anonymous broker on `campingpi:1883` (Phase-0 stopgap; repoint to the N100 later).

- `sally/telemetry/lte/state` *(retained JSON)* — `up_bps`/`down_bps`,
  `up_kbps`/`down_kbps`, `tx_bytes_total`/`rx_bytes_total`, `signal_dbm`,
  `rssi_csq`, `rssi_pct`, `operator`, `network`, `conn_status`, `sim_status`,
  `sim_slot`, `modem_model`, `router_uptime`, `ts`.
- `sally/telemetry/lte/status` *(retained)* — `online` / `offline`.
- `homeassistant/sensor/sally_lte_*/config` *(retained)* — HA auto-discovery for 9
  sensors (uplink, downlink, signal dBm, RSSI %, operator, network, status,
  up/down totals), grouped under device **"Sally LTE Modem"**. Hard-death is caught
  by `expire_after` (3× interval); clean shutdown publishes `offline`.

Quick look from the Pi: `mosquitto_sub -h 127.0.0.1 -t 'sally/telemetry/lte/#' -v`

## Deploy / operate

```sh
./scripts/deploy-lte-monitor.sh                 # reads QX210_LUCI_PASS from repo .env
ssh pi@10.66.12.216 'journalctl -u sally-lte-monitor.service -f'
```

## Limitations / next

- dBm + CSQ only (no RSRP/RSRQ/SINR — modem firmware limit).
- Depends on LuCI HTML/JSON staying stable across any router firmware change.
- When the **N100** takes always-on services, move the broker there and repoint
  `MQTT_HOST`; the poller itself can run anywhere that can reach the router.
- Bridge `campingpi`'s mosquitto to the homeController HA/Grafana to graph history.
