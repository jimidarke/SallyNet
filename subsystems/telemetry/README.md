# Telemetry — Fuel Economy vs Conditions

The goal: stop guessing why Sally's mpg varies trip-to-trip and start *seeing* it. Correlate fuel economy with outside temperature, elevation gain, grade, speed, ambient pressure, engine bay heat, and odometer — recorded on the Pi, joined against a manual fuel log, surfaced on a dashboard.

The 460 V8 is going to be thirsty no matter what (see `docs/about-sally.md`), but the *shape* of the thirst is interesting: how much does a steep climb cost? Does that air-intake cutout actually help highway cruising? Does an engine-bay temperature spike correlate with mileage drops?

## Status

Not built. Planning + parts inventory.

> **ESP node contract:** the shared conventions for every ESP32 sensor/input node (firmware, MQTT
> topic shape, broker, power, secrets) + the full node catalog + build order live in
> [`esp-fleet.md`](esp-fleet.md). This README owns the fuel-economy *goal* and the Pi-hosted
> collector pipeline; `esp-fleet.md` owns the node fleet.

## Inputs we can capture today

| Signal | Source | Hardware | Notes |
|---|---|---|---|
| **Wheel speed / distance** | BLE bike speed sensor on a rear wheel hub | Existing user-owned BLE rotation sensor(s) | Accelerometer-based, BLE CSC profile (UUID 0x1816). Reports cumulative wheel revolutions + last event timestamp. Works on **any** rotating thing. |
| **GPS speed + position + altitude** | gpsd on Pi (see `subsystems/gps/`) | VK-162 USB GPS | GPS altitude is jittery — use barometric for smooth elevation, GPS for absolute position |
| **Barometric pressure + outside temp + humidity** | I2C sensor on Pi | BME280 (~$5) | Best altimeter signal short of an aircraft instrument. Mount near a cabin vent for outside air, not on a heat source. |
| **Engine bay temperature** | 1-wire probe wired into the bay | DS18B20 waterproof probe (~$3) | Robust, long cable run, good for monitoring the 460's heat profile especially with the air-intake mod |
| **Manual fuel log** | Human at each fill-up | Phone, paper, anything | See `docs/fuel-log.md` — the source of truth for litres in and odometer reading |

## Why BLE wheel speed instead of just GPS speed?

GPS speed is great on the highway but flakey in canyons / dense forest / parking lots. A BLE wheel sensor:
- Gives you instantaneous speed even with no satellite fix
- Acts as an independent odometer you can sanity-check GPS distance against
- Gives a "true" odometer that doesn't drift when the truck is parked
- Doesn't burn data — it's all local BLE

The catch: **calibration.** Bike apps cap wheel size at bike values; here you're writing your own consumer (Python `bleak` library, dead simple) and feeding it Sally's actual tire circumference. That goes in `configs/telemetry/wheel.yaml`.

### Tire circumference calibration

When the sensor is mounted:
1. Inflate to spec (placard on the driver door jamb)
2. Mark the tire and ground at touchdown
3. Roll the truck one full revolution, mark the new ground touchdown
4. Measure between the marks — that's your circumference in mm (loaded, not nominal)
5. Write it into `configs/telemetry/wheel.yaml`

Re-calibrate when tires are replaced or air pressure changes by more than ~5 psi.

## Pipeline sketch

```
   ┌──────────────────────┐
   │ BLE wheel sensor     │── BLE CSC ──┐
   └──────────────────────┘             │
   ┌──────────────────────┐             │
   │ BME280 (I2C)         │── i2c ──────┤
   └──────────────────────┘             │
   ┌──────────────────────┐             ▼
   │ DS18B20 (1-wire)     │── 1-wire ─► Pi 3B
   └──────────────────────┘             │
   ┌──────────────────────┐             │
   │ gpsd (USB GPS)       │── socket ───┤
   └──────────────────────┘             │
                                        │
                                        ▼
                              ┌─────────────────┐
                              │ collector       │  Python; samples each
                              │ (Python service)│  source on its own cadence,
                              └────────┬────────┘  writes a unified record
                                       │
                                       ▼
                              ┌─────────────────┐
                              │ SQLite on Pi    │  rolling local store +
                              │ (or InfluxDB,   │  fuel-log join on import
                              │  if scaling)    │
                              └────────┬────────┘
                                       │
                                       ▼ (over QX210 WiFi when home, or 4G)
                              ┌─────────────────────────┐
                              │ Home Assistant /        │  Grafana panel:
                              │ Grafana on homeController│  mpg vs grade, bay
                              │ estate                  │  temp vs RPM, …
                              └─────────────────────────┘
```

## Phase plan

1. **Phase 0 — Manual fuel log only.** Just start filling in `docs/fuel-log.md` at every fuel stop. Zero hardware. Even on its own this answers "what's Sally's real-world mpg?"
2. **Phase 1 — GPS + BME280 on the Pi.** Adds elevation gain, outside temp, route. `gpsd` is already on the roadmap for `subsystems/gps/`; piggyback on it.
3. **Phase 2 — BLE wheel sensor.** Mount on a rear hub, calibrate. Write a small `bleak` consumer that subscribes to the CSC characteristic and logs to the same store.
4. **Phase 3 — Engine bay DS18B20.** 1-wire run from the cabin Pi into the bay. Useful in its own right (overheating alarm).
5. **Phase 4 — Correlation views.** Once there's a month of data, build Grafana / HA dashboards: mpg vs grade, mpg vs temp, bay-temp vs sustained load, elevation gain per trip leg.

## Cabin UI — pinpad + small screen on the Pi

> **SUPERSEDED (2026-06-26):** fuel-log *entry* now lives on a dedicated **ESP32 + 4×4 keypad + OLED at the driver's door** that HTTP-POSTs to `sally-api` `/api/fuel-log` (see `subsystems/media/api-contract.md`). Fuel entry is **not** on the Roku (the Roku only displays derived economy). The cabin-pinpad-on-the-Pi/HDMI design below is kept for reference only.

The telemetry pipeline is only useful if entering a fuel-log row or glancing at "what's the bay temp right now?" is **frictionless**. Right now `docs/fuel-log.md` is markdown — fine for first entries, terrible at a gas station in the rain. The fix is a small dedicated UI in the cabin.

### Hardware

| Component | Options | Notes |
|---|---|---|
| **Input device** | Wireless numeric pinpad with USB-dongle (Logitech / generic 2.4 GHz numpads, ~$15–25); or a BLE numeric keypad; or a few big arcade buttons wired to GPIO | A USB-dongle numpad is the path of least resistance — appears to Linux as a HID keyboard, no pairing flakiness, no BLE budget on the Pi |
| **Display** | 3.5" or 5" SPI/HDMI Pi-hat touchscreen, OR a generic small HDMI monitor mounted in the cabin | The Pi 3B already has HDMI out. If you want it always-on alongside the existing HDMI selector, a tiny dedicated HDMI screen wired straight to the Pi (separate from the entertainment HDMI selector) is cleaner. |
| **Mount** | Wherever the navigator riding shotgun can reach without unclipping | Avoid the driver's reach zone — this is a log-and-glance device, not a control panel |

### What it does

A small Python or web (kiosk-mode Chromium) app on **the mini-PC** (see `subsystems/compute/`) that boots into a fullscreen dashboard on a small HDMI screen in the cabin. Pinpad input is also the **audio source-switcher control** (cross-linked from `subsystems/audio/source-switcher.md`): keys 1–4 pick the audio source, 5–7 control mute/FM/BT, 8–9 + telemetry-mode key handle log entry. PA push-to-talk is **not** on the pinpad — it's the dedicated button on the QX-18 mic in `subsystems/audio/pa-mode.md`.

Two modes flipped with the same pinpad:

**Glance mode (default, idle):**
- Big numbers: current speed (BLE wheel sensor), outside temp (BME280), bay temp (DS18B20), cabin battery voltage (`subsystems/power/` shunt feed)
- Trip subtotal: km this trip, average L/100 km since last fill, elevation gain so far
- A status strip across the bottom: GPS fix Y/N, BLE sensor connected Y/N, network (cell vs WiFi-as-WAN vs offline)

**Log mode (triggered by a pinpad key — e.g. `*` or `Enter`):**
- A guided form: odometer → litres → cost → notes (notes can be skipped). Pinpad-friendly: number keys + Enter.
- Writes an entry to the telemetry store **and** appends a row to `docs/fuel-log.md` so the markdown stays the source of truth that survives even if the Pi dies
- Quick-entry macros on the pinpad: `1`-`9` could trigger common notes ("highway only", "rain", "mountain pass", etc.) — assign these once in `configs/telemetry/pinpad-macros.yaml`

### Implementation notes

- USB HID pinpads appear as `/dev/input/event*` — Python `evdev` reads keypresses cleanly without grabbing the OS keyboard
- The Pi 3B already runs RetroPie. If telemetry runs on the same Pi (see `subsystems/compute/` re: cohabitation), pinpad + screen need to **not** interfere with RetroPie input — easiest answer is to give telemetry its own Pi (cheap, like a Pi Zero 2 W or another 3B), and let RetroPie keep the controllers
- Or: make telemetry a service that's only active when no controller is connected, swap modes by pinpad key combo
- The fuel-log markdown table is the system of record; the Pi UI is just a convenient editor

### Phase plan for the cabin UI

Slots in alongside the telemetry phases above:
- **Phase 1.5 — Glance mode only.** Display whatever sensors are live; no log input yet. Pinpad not needed.
- **Phase 2.5 — Log mode + pinpad.** Add the fuel-log form. Pinpad does the entry.
- **Phase 3.5 — Macros + alarms.** Bay-temp threshold alarm flashes the screen; pinpad macros for common log notes.

## Reference

- BLE CSC profile spec: Service UUID `0x1816`, Measurement characteristic `0x2A5B`. Each notification carries cumulative wheel revolutions (uint32) and last wheel event time at 1/1024 s resolution.
- `bleak` (Python BLE library): https://github.com/hbldh/bleak
- BME280: stock in Adafruit / generic Chinese breakouts; I2C address typically 0x76 or 0x77
- DS18B20: 1-wire on the Pi via `w1-gpio` overlay; many tutorials

## Next action

Start `docs/fuel-log.md` immediately. Every fill-up entry — even with no sensors yet — is data you'll wish you had later when Phase 2 lands.
