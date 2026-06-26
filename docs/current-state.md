# Current State — Sally's Installed Tech

Snapshot of what's physically in Sally right now. Update this whenever something is installed, removed, or replaced. Roadmap items (planned but not built) live in each subsystem's README, not here.

Last updated: 2026-06-26

## Network

| Component | Model / Notes |
|---|---|
| Router / 4G LTE backbone | **QX210-NW2 Industrial 4G LTE WiFi Router** — LEDE/OpenWrt based, LuCI web UI. LAN **192.168.2.1**, SSID **SallyNet** (`192.168.2.0/24`). RS232 port is a **data DTU** (Modbus RTU↔TCP, TCP passthrough) — *not* a console port. Manage over SSH / web UI. |
| Cell antenna | Roof-mount **directional** antenna on extending spire mount |
| Cell signal booster | **ANNTLENT** 850 / 1900 / 700 MHz cell booster — Bands 2 / 5 / 12 / 17, sized for Canadian LTE 4G / 3G / GSM carriers (home/cottage class) |
| Pi ↔ router serial link | **GPIO UART ready, not yet wired.** `/dev/serial0` → `ttyAMA0` (PL011) on the Pi 3B+, freed by disabling Bluetooth + `enable_uart=1`, serial console stripped. No USB-RS232 adapter is present (earlier doc claim was wrong). Before wiring: **meter-check the router port's level** (3.3V TTL vs true RS-232). Validated pinout + plan in `subsystems/network/router-serial-uart.md`. |

## Media (main entertainment panel)

| Component | Model / Notes |
|---|---|
| TV | **Pyle TV** with built-in DVD player |
| Media player | **AGPtek mini 1080p** (USB / SD) |
| Roku | **Roku Premiere "Camperoku"** (3920CA, OS 15.2.4) at **192.168.2.227** on SallyNet wifi. Streams Netflix etc.; runs the sideloaded SallyNet channel (forked from sibling `rokuApp`/HouseWall). **Developer Mode ON** (verified 2026-06-26) — SallyNet channel sideloaded + verified running (dev IP + devpw in CLAUDE.md). |
| Backup-cam head unit | **9" TFT 4-camera live-view backup camera** with RCA composite video out |
| HDMI / video routing | HDMI input selector between the above sources; backup-cam RCA is currently a standalone display, not yet routed through the selector |
| Existing media server | **MiniDLNA "CampingNetMedia"** on the Pi (`campingpi:8200`) already serves movies/TV from the HDD over the LAN — candidate source for the Roku channel. **Decision (2026-06-26):** the Roku uses `sally-api` `/api/media` (encode-once MP4 over HTTP Range); MiniDLNA is retired for the Roku path. |

## Compute

| Component | Model / Notes |
|---|---|
| Raspberry Pi 3B+ | (Rev 1.4 — *not* the plain 3B previously documented.) Hostname **`campingpi`** at **192.168.2.216** (Raspbian Buster, **wired eth0**). **Not a pure RetroPie box** — also runs **Samba** (`roms`/`bios` shares, :445), **MiniDLNA "CampingNetMedia"** (:8200, serving movies/TV off the HDD), and a tiny Flask **"System Metrics"** page on :80 (psutil host stats; runs as root, no auth). Also runs **sally-api** on :8090 — the single HTTP surface the SallyNet Roku channel polls (`/api/state` live from gpsd); code in `services/sally-api/`, systemd `sally-api.service`. RetroPie + 2× USB controllers (USB pads, not BT) still present. **WiFi + Bluetooth disabled** (unused; BT-disable also frees the UART). Remote access via WireGuard → `subsystems/network/remote-access-vpn.md`. ⚠️ Chronic under-voltage — browns out during boot (`get_throttled` hits `0x50005` live), see `subsystems/power/`. |
| Storage | **~1 TB USB HDD** (931.5 GB, **exFAT**) at `/mnt/usb` — *not* the "500 GB" previously documented. Already holds `media/movies`, `media/tv`, and `shared`, served on the LAN via the Pi's MiniDLNA. RetroPie roms live on the SD card, not here. |

## GPS

| Component | Model / Notes |
|---|---|
| GPS receiver | **u-blox 8 GNSS** (UBX-M8030, USB ID `1546:01a8`) on the Pi — `/dev/ttyACM0`, stable by-id `usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00`. Multi-GNSS (GPS + GLONASS + SBAS). Plugged in 2026-06-26. |
| gpsd | **Installed + active** — `gpsd 3.17`, socket-activated, reads the by-id device with `-n`, serves JSON on `localhost:2947`. Verified live **3D DGPS fix** (HDOP ~0.65, ~12 sats). Config `/etc/default/gpsd`; apt repointed to `legacy.raspbian.org` to install (Buster EOL). |

## Rear panel

| Component | Notes |
|---|---|
| USB charging ports | Gadget charging when shored |
| Voltage indicator | Quick house-battery status read |
| **Uniden** FRS handheld charging stations | Multiple — see comms inventory |

## Tanks

| Component | Model / Notes |
|---|---|
| Fresh / grey / black holding tanks | Each with 4–5 stacked vertical probe electrodes, original 1980s design. Pigtail to dash panel reads E/⅓/⅔/F. **Currently flaky** — typical fouling and corrosion. Tank material (plastic/poly vs steel) **not yet confirmed** — gates retrofit choice. |
| Propane tank | Large under-floor tank feeding the furnace. **HANDS OFF.** No hobbyist modification of tank, regulator, OPD valve, lines, or flex hoses. Only non-invasive additions allowed (leak detector, external magnetic level sensor). |

## Plumbing

| Component | Notes |
|---|---|
| Water pump | **DPHCF42-12V** — recently replaced, works well |
| Hot water tank | Working well — model TBD |
| Bathtub | Interior tub (Okanagan RB / Rear Bath floorplan) |
| Sewage connector | Replaced 2 years ago |
| Fridge | **Dometic RM763** — **broken**, used as storage |
| HVAC | Furnace works great. **No air conditioning.** |

## Power — 12V system

| Component | Model / Notes |
|---|---|
| Engine batteries | **2× 12V @ 800 CCA each** — main starting + chassis loads |
| Engine ↔ house tie | 12V disconnect + manual switch (the "badass switch") joining engine bank to the house battery for starting support |
| House battery | **~600 CA car battery** (single, rear) |
| Converter / charger | **Progressive Dynamics PD4135KW2B** — 35A 12V converter with Charge Wizard pendant |
| Battery feed | 20A inline fuse on the positive run from converter to house battery; 1 AWG run to the engine battery cutoff for starting support |
| Status | Voltage drops symptomatic — see `subsystems/power/` for the diagnose-first plan |

## Power — AC breaker map

| # | Circuit |
|---|---|
| 1 | Battery charger (PD4135KW2B) |
| 2 / 3 | Shore power |
| 4 | Inverter — **disconnected** |
| 5 | Kitchen plug |
| 6 | Exterior plug |

## Power — DC loads (from house panel)

- Rear panel
- Main panel (TV, media player, Roku, Pi, router, backup cam head)
- Cabin lights (2× circuits)
- Furnace

## Comms

| Component | Model / Notes |
|---|---|
| FRS handhelds | **Uniden** family pack — kids' loaners. Lossy: get broken, lost, scattered. Inventory + channel plan to be captured in `subsystems/comms/`. |
| Cell booster | See **Network** above — same ANNTLENT unit |
