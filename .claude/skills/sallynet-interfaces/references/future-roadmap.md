# Future user-facing interactions (planned — not built)

Everything here is **planned**, marked with its status. Scope is locked but hardware is
mostly unbought. Don't describe these as working.

## RF camper-to-camper voice — amateur radio (planned, design done)

**Authoritative:** `subsystems/comms/amateur-radio-path.md`.

The vision: two vehicles in the BC backcountry talk driver-to-driver over **licensed
amateur radio** — 2 m (144–148 MHz) + 70 cm (430–450 MHz) dual-band mobiles, 5–30 km
simplex extended via the BC repeater network. Requires the Canadian **Basic
Qualification** (free exam, permanent callsign). Rough kit: an Anytone/Yaesu dual-band
mobile (~$280–400) + a mag-mount NMO antenna, powered from the house battery, fused.

> ⚠️ **Do not conflate with the FM transmitter.** The BETS-1 FM transmitter is for
> **cabin-range music broadcast only** (< 1 µW EIRP, strict compliance) — never a voice
> channel. Camper-to-camper voice is amateur radio, full stop. FRS handhelds (license-
> exempt, 2 W) already cover kids-at-the-campsite chatter; amateur is the adult,
> licensed, vehicle-to-vehicle path. Three different things — keep them straight.

Not built: no rig, no antenna, no licensing done yet. This lives outside the SallyNet
codebase (it's a radio stack, not software).

## ESP32 nodes people interact with (planned)

**Authoritative:** `subsystems/telemetry/esp-fleet.md` (8-node catalog, locked contract).

Most of the fleet is passive sensing (no user input): cabin env, env satellites, a
battery fireside node, tanks, power. Two nodes are **human inputs**:

- **#5 fuel-keypad** — 4×4 keypad + OLED at the driver door; enters a fill-up and
  `POST`s the **same `/api/fuel-log`** the web `/fuel` page uses. Replaces the phone form
  on long trips. The web form is already built; this is the hardware twin.
- **#6 back-seat ETA** — a button + OLED ("are we there yet?"). On press it does
  `GET /api/state` and shows `trip.km_to_dest` / `trip.eta`. Pure consumer of existing
  fields — no new sensors, no contract change. Scoped to ETA only (no call/scene buttons).

Conventions every node obeys: ESPHome firmware, MQTT topics `sally/telemetry/<area>/…`,
broker `192.168.2.216:1883` (host in `secrets.yaml`), 12 V→5 V buck power. Readings reach
the Roku/back-seat OLED only via `/api/state` (glass over HTTP), through a planned
`telemetry-collector.py` that folds MQTT into the API's reserved `env/tanks/power/level/
systems` blocks. Build order starts with the cabin node (#0, config already written).

## WLED ambient lighting (planned)

**Authoritative:** `subsystems/lighting/README.md`.

Soft LED zones (front lounge, rear bunk) on WS2811 12 V strips driven by an ESP32 running
**WLED** — warm-white reading / dimmable nightlight presets, eventually an MQTT/HA bridge.
Same hardware recipe as the sensor nodes (12 V→5 V buck, level shifter, inline fuse, power
injection on long runs). Bench-test a kit before any cabin install. No current user-facing
interaction beyond static presets.
