# Compute

**Decision (v0.2.0): mini-PC (Intel N100 class) will host always-on services; the Pi 3B+ then returns to being a pure RetroPie appliance.** (Today it's a hybrid, not pure RetroPie — see Status.)

Why: The Halloween project hit the ESP32 (and by extension Pi 3B-class) limit hard — single radio time-slicing WiFi and BT makes A2DP + Snapcast cohabitation unreliable. The mini-PC has separate physical WiFi and BT radios, so Snapcast-over-WiFi-while-streaming-A2DP-to-a-BT-speaker-while-feeding-an-FM-transmitter all works concurrently. Mini-PC also has the headroom for telemetry collector + Roku media HTTP + MQTT broker + gpsd on the same host without service-cohabitation headaches.

Pi 3B+ (Rev 1.4) + ~1TB HDD + 2× USB controllers. **Today it is NOT pure RetroPie** — it also runs Samba, MiniDLNA ("CampingNetMedia"), and a Flask metrics page, and hosts the WireGuard remote-access site node (`subsystems/network/remote-access-vpn.md`). The v0.2.0 plan moves those always-on services to the mini-PC; the HDD migrates too and the Pi gets a fresh SD card with RetroPie only.

## Status

- **Working:** RetroPie boots, 2× USB controllers, HDD mounted, games run. Also serving Samba + MiniDLNA + Flask metrics, plus a WireGuard site node for remote access.
- **2026-06-26 changes:** WiFi + Bluetooth **disabled** (wired-only; also frees the UART); `enable_uart=1` + serial console stripped → `/dev/serial0` (PL011) ready for the router DTU link (`subsystems/network/router-serial-uart.md`); RetroPie Tier-1 config fixes applied (`subsystems/media/retropie-notes.md`).
- **Serial:** no USB-RS232 adapter is actually present (earlier plan) — the link will use the **GPIO UART** instead.
- ⚠️ **Power:** chronic under-voltage / boot brown-outs — see `subsystems/power/`.

## Roadmap

All the always-on services land on the mini-PC, not the Pi:

1. **Media HTTP server** for the Roku channel (`subsystems/media/`) — **already live on the Pi** as `sally-api` (Flask, `:8090`) serving `/api/media?type=trips` + `/api/collections/<id>` + `/api/photos` + `/media/<path>` (Range), plus the encode/ingest pipeline at `/opt/sally/media/`. At Phase 3 this moves to the mini-PC (HDD `home/` tree migrates to `/srv/sally-media/`); the Roku just repoints `apiBase`.
2. **GPS tracker** (`subsystems/gps/`) — gpsd + Traccar client on the mini-PC
3. **MQTT broker** — mosquitto on the mini-PC for WLED + power + tank + telemetry sensors to publish into; bridge home to the existing Home Assistant estate (see `homeController`)
4. **Telemetry collector** (`subsystems/telemetry/`) — Python service on the mini-PC reading BLE wheel speed, BME280, DS18B20, gpsd; writing to SQLite
5. **Audio stack** (`subsystems/audio/`) — snapserver + MPD + librespot + PipeWire + PA mic capture, all on the mini-PC
6. **RetroPie game manifest** — capture the current ROM library + controller mapping into `configs/compute/retropie-manifest.md` so a wipe is recoverable. Stays on the Pi.

## Next action

Procure the mini-PC and a 12 V → 19 V step-up converter — that's a **boost** topology, not buck (going *up* in voltage). Better still: a **buck-boost** converter, because Sally's "12 V" house-battery bus is actually 11.5 V (low SoC) up to 14.4 V (bulk-charging). A pure boost still works (Sally's bus is always below 19 V), but a buck-boost is more forgiving if the bus ever spikes. Sized for ~6 A output (the mini-PC pulls ~3–4 A peak at 19 V). Pick a fanless or low-fan N100 (Beelink Mini S12, GMKtec G3, etc.) with 16 GB RAM + 256–512 GB NVMe. Mount somewhere ventilated in Sally (not the propane locker — see `subsystems/tanks/`). First-boot is Ubuntu Server 24.04 LTS + Docker; everything else layers on top.
