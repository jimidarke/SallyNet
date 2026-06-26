# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SallyNet is the single source of truth for everything bolted into **Sally** — a 1985 Ford Okanagan Kelowna motorhome used for family camping in BC. It covers both the rolling tech stack (network, media, compute, lighting, comms, sensors, GPS, power) and a small mechanical reference for the chassis itself.

**Stack:** Markdown documentation + (eventual) Bash scripts + ESPHome/WLED YAML + BrightScript/SceneGraph for a sideloaded Roku channel (forked from sibling project `rokuApp`).

## Architecture

Three-layer organisation:

1. **Top-level docs** (`docs/`) — human-readable: `about-sally.md` (bio), `mechanics.md` (chassis/drivetrain reference), `current-state.md` (live inventory), `network-diagram.md` (how things connect).
2. **Subsystems** (`subsystems/<name>/`) — one folder per functional area: `network`, `media`, `compute`, `lighting`, `comms`, `gps`, `tanks`, `power`, `telemetry`, `audio`. Each has a README with status + next concrete action, plus any subsystem-specific notes, exports, or diagrams.
3. **Scripts + configs** (`scripts/`, `configs/<subsystem>/`) — bash tooling and config templates, organised to mirror `subsystems/`.

## Key Conventions

- All bash scripts use `set -euo pipefail`
- Colored output via shared helper functions: `header()`, `ok()`, `warn()`, `fail()` using ANSI codes (RED/GREEN/YELLOW/CYAN/NC) — same style as sibling project `gameBox`
- Config templates use `REPLACE_WITH_*` placeholders
- Subsystem READMEs always end with a "Next action" line so the project never goes stale without it being obvious
- Propane system (tank, regulator, lines, OPD valve, flex hoses) is **read-only** — only non-invasive additions allowed (leak detector, external magnetic level sensor). Documented explicitly in `subsystems/tanks/README.md`.
- Roku channel source lives in this monorepo at `roku-channel/` (forked off `rokuApp/HouseWall`, consolidated from a separate repo 2026-06-26); `subsystems/media/` holds the deploy/integration docs + the frozen `/api` contract
- **Mini-PC (planned, Intel N100 class) takes always-on services** (audio, telemetry, Roku media HTTP, MQTT broker, gpsd). **As of 2026-06-26 the Pi hosts gpsd + `sally-api` as the Phase-0/2 stopgap; these migrate to the N100 at Phase 3.** Pi 3B+ stays the pure RetroPie appliance. Rationale: ESP32 / Pi 3B+ time-slice WiFi and BT on a single radio (lesson from the Halloween project); the mini-PC has separate physical radios, no conflict. (WiFi + BT are now **disabled** on the Pi — it's wired-only — which also frees the PL011 UART for the router serial link.)
- **FM transmitter is for music broadcast within Sally and immediate vicinity only** — strict BETS-1 compliance (< 1 µW EIRP). Never the voice channel. Camper-to-camper voice = amateur radio (see `subsystems/comms/amateur-radio-path.md`).

## File Paths on Sally's hardware

```
# Mini-PC (planned — Intel N100 class, always-on services host)
/var/lib/mpd/music/                        # 500 GB HDD migrated from Pi; music library
/etc/snapcast/snapserver.conf              # Snapcast multi-room sync
/etc/mpd.conf                              # MPD → snapserver FIFO
/etc/librespot/librespot.toml              # Spotify Connect endpoint "Sally"
/srv/sally-media/                          # Roku channel media HTTP service mounts here
/opt/pa-duck/                              # QX-18 PTT capture + ducking service

# Raspberry Pi 3B+ (Rev 1.4, in cabinet behind TV) — RetroPie ONLY post-mini-PC migration; WiFi+BT disabled, wired eth0
/home/pi/sally-media/                      # (legacy) HDD mount — moves to mini-PC at Phase 1
/etc/gpsd.conf                             # (legacy) gpsd moves to mini-PC
/opt/traccar-client/                       # (legacy) Traccar client moves to mini-PC
/dev/serial0  ->  ttyAMA0                  # PL011 UART (BT disabled + enable_uart=1) — ready for the QX210 RS232/DTU link
# campingpi reachable remotely at 10.66.12.216 via the WireGuard site node (see subsystems/network/remote-access-vpn.md)

# QX210-NW2 router (manage over SSH from Pi)
/etc/config/network                        # UCI: WAN profiles for cell vs WiFi-as-WAN
/etc/config/wireless                       # UCI: SSID + WiFi-repeater config

# Roku (sideloaded SallyNet channel) — "Camperoku", Roku Premiere 3920CA, OS 15.2.4
# Dev IP: 192.168.2.227  (SallyNet DHCP — verified 2026-06-25)
# DevPassword: ROKU_DEV_PASSWORD in the gitignored roku-channel/.env (Camperoku-specific — does NOT match the HouseWall fleet's)
# Developer Mode currently ON — verified 2026-06-26; SallyNet channel sideloaded (source at roku-channel/). Re-enable sequence if ever factory-reset: Home×3 Up Up R L R L R.
```

## Versioning

Uses semantic versioning in `VERSION.txt` (line 1 = version, followed by changelog). Tags prefixed with `v` (e.g., `v0.1.0`). Commits follow Conventional Commits format. Bump on every subsystem land, not on every doc tweak.

## Reference projects (siblings — do NOT modify from this repo)

- `~/code/gameBox` — template for folder shape, CLAUDE.md style, bash conventions
- `~/code/rokuApp` — HouseWall, the production sideloaded SceneGraph channel that the SallyNet channel (roku-channel/) forked from

## Hardware Context

Sally is a **1985 Ford E-350 Econoline cutaway** (Okanagan Kelowna coachwork) — VIN `…B40728`, built at Ford's Lorain OH plant, **7.5L (460 cu in) V8 EFI**, GVWR 4989 kg (~11,000 lb), GAWR 1905/3356 kg front/rear. The 460 V8 is famous for being very thirsty — fuel economy expectations are in the 6–8 mpg range.

Notable quirks: dual gas tank with a crossed selector valve (gauge shows front, engine pulls from rear when switch is in FRONT position; switching to REAR shows correct rear level but stalls in minutes — fuel line replumb only treated the symptom). Power steering, foot-press high-beam switch, factory CD player.

**12V house system:** 2× 800 CCA engine batteries with a 12V disconnect + manual switch tying them to a single ~600 CA house battery in the rear. House battery is charged by a **Progressive Dynamics PD4135KW2B** (35 A converter) through a 20 A inline fuse at the battery positive. A straight 1 AWG link runs to the engine battery cutoff for starting support.

**AC breakers:** (1) battery charger, (2/3) shore, (4) inverter — *disconnected*, (5) kitchen plug, (6) exterior plug.
**DC loads:** rear panel, main panel, lights ×2, furnace.

House systems include fresh/grey/black holding tanks with 1980s-era stacked-probe level sensors, a large underfloor propane tank feeding the furnace, and the above 12V system showing voltage-drop symptoms. Broken **Dometic RM763** fridge (storage only); new **DPHCF42-12V** water pump; **no air conditioning**. Network backbone is a QX210-NW2 industrial 4G LTE router with a roof-mount directional cell antenna feeding an **ANNTLENT** Band 2/5/12/17 indoor signal booster. Backup-cam system is a 9" TFT 4-camera head unit with RCA video out — viable input source for future Roku channel work.
