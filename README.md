# SallyNet

Everything about **Sally** — our 1985 Ford Okanagan Kelowna motorhome — in one place. Both the tech that's been bolted in over the years and a small mechanical reference for the chassis itself.

## Start here

- [docs/about-sally.md](docs/about-sally.md) — who Sally is, her quirks, the bio
- [docs/current-state.md](docs/current-state.md) — what's installed right now (inventory snapshot)
- [docs/network-diagram.md](docs/network-diagram.md) — how the boxes are wired together
- [docs/mechanics.md](docs/mechanics.md) — chassis / drivetrain reference for the road
- [docs/fuel-log.md](docs/fuel-log.md) — fill-up log (start filling this in today)

## Subsystems

Each folder under `subsystems/` covers one functional area. Each one has a README with current status and the next concrete action.

| Folder | What it covers |
|---|---|
| [`subsystems/network/`](subsystems/network/) | QX210-NW2 4G LTE router, WiFi-as-WAN, captive portal handling |
| [`subsystems/media/`](subsystems/media/) | TV, HDMI selector, Roku (sideload target), USB/SD player |
| [`subsystems/compute/`](subsystems/compute/) | Raspberry Pi 3B+ + ~1TB HDD + RetroPie + Samba/DLNA media server |
| [`subsystems/lighting/`](subsystems/lighting/) | WLED ambient lighting (ESP32 + WS2811 12V strips) |
| [`subsystems/comms/`](subsystems/comms/) | FRS family radios, cell booster |
| [`subsystems/gps/`](subsystems/gps/) | VK-162 USB GPS, gpsd, Traccar |
| [`subsystems/tanks/`](subsystems/tanks/) | Fresh/grey/black tank level sensors, propane (hands-off) |
| [`subsystems/power/`](subsystems/power/) | 12V house battery, charging, voltage-drop diagnosis, shunt monitor |
| [`subsystems/telemetry/`](subsystems/telemetry/) | Fuel economy vs conditions, BLE wheel sensor, BME280, engine bay temp, cabin pinpad UI |
| [`subsystems/audio/`](subsystems/audio/) | One source switcher → Snapcast over WiFi + BT speakers + FM broadcast; QX-18 handheld PTT for PA |

## Conventions

- Roadmap and rationale live in [docs/](docs/) and each subsystem README.
- Bash scripts use `set -euo pipefail` and the shared helper style from sibling project `gameBox`.
- Roku channel source lives in its own forked repo, not here — `subsystems/media/` only holds deploy + integration notes.
- **Propane system is read-only.** No hobbyist modification of tank, regulator, lines, or hoses. See [`subsystems/tanks/README.md`](subsystems/tanks/README.md) for what is and isn't fair game.
