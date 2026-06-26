# Lighting — WLED Ambient Strips

Soft ambient lighting around the cabin for late-night reading and general "make camping feel like home" mood. ESP32 + WS2811 12V LED strips, WLED firmware.

## Status

Not built yet. Planning + parts list only.

## Hardware recipe (per WLED 12V camper guidance)

- **WS2811 12V strips** (NOT 5V WS2812 — voltage drop over a long run will wreck colour consistency)
- **74AHCT125 level shifter** on the data line — mandatory for reliable signal from a 3.3V ESP32 to a 5V data input
- **Inline fuse** on the +12V feed off Sally's house battery (size to strip max draw)
- **12V → 5V buck converter** for the ESP32. Do **not** feed the ESP32 raw RV 12V — alternator and charger transients will eventually kill it.
- **Power injection every ~5 m** on long runs; strip current adds up fast

References:
- [WLED Wiring Pro Tips](https://kno.wled.ge/advanced/wiring/)
- [WLED 12V van setup thread](https://wled.discourse.group/t/help-for-12v-van-setup/10622)

## Zones (proposed)

| Zone | Strip length | ESP32 location | Notes |
|---|---|---|---|
| Front lounge | TBD | Hidden in valance | Warm-white default for reading |
| Rear bunk / bed | TBD | Behind headboard | Dimmable nightlight mode |

Add zones as the project grows. Keep one ESP32 per zone — simpler wiring, no long data runs.

## Roadmap

1. Measure each zone's strip length; size 12V supply + fuse accordingly.
2. Flash WLED to an ESP32 (start with one zone end-to-end before scaling).
3. Capture each zone's WLED preset JSON into `configs/lighting/<zone>-presets.json`.
4. Bridge to Home Assistant (over MQTT) once a Pi-side broker exists.

## Next action

Buy a test kit (one ESP32 + buck converter + level shifter + 1m of WS2811 12V strip + fuse holder) and prove the wiring recipe on the bench before doing any in-cabin install.
