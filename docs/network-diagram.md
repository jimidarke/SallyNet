# Network Diagram

How Sally's boxes are wired together as of 2026-05-17. Update when topology changes.

**Planned addition (v0.2.0):** an Intel N100-class mini-PC becomes the always-on services host (audio, telemetry, Roku media HTTP, MQTT broker, gpsd) — shown dashed below until it physically lands. Pi 3B+ stays as the pure RetroPie appliance (today it's a hybrid — also Samba/DLNA/metrics + a WireGuard site node; see `subsystems/compute/`).

## Logical topology

```
                ┌─────────────────────────────┐
                │   Roof: directional cell    │
                │   antenna (spire mount)     │
                └──────────────┬──────────────┘
                               │ coax
                ┌──────────────▼──────────────┐
                │  ANNTLENT cell booster      │
                │  (Bands 2/5/12/17 — indoor) │
                └─────────────────────────────┘
                       (over-the-air boost,
                        no direct link to router)

   4G LTE WAN                  WiFi LAN
       │                         │
       ▼                         ▼
┌──────────────────────────────────────────────┐
│  QX210-NW2 Industrial 4G LTE WiFi Router     │
│  (LEDE/OpenWrt; SSH-managed)                 │
│                                              │
│  WAN options:                                │
│   - Cell uplink (default on the road)        │
│   - WiFi-as-WAN (planned: home / campground) │
│                                              │
│  RS232 port → DTU only (not console)         │
└────────┬──────────────────────┬──────────────┘
         │ WiFi                 │ eth0 (wired LAN) · UART idle
         │                      │
         ▼                      ▼
┌──────────────────┐   ┌─────────────────────────┐    ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
│ Roku             │   │ Raspberry Pi 3B+        │      Mini-PC (Intel N100,
│ (Netflix +       │   │  - RetroPie + 2 ctrls   │    │ planned v0.2.0)         │
│  future Sally    │   │  (after v0.2.0: pure    │      - Snapcast server
│  channel via     │   │   RetroPie appliance)   │    │ - MPD + librespot       │
│  sideload)       │   │                         │      - PipeWire audio graph
└────────┬─────────┘   │  (SSD migrates to       │    │ - gpsd + Traccar        │
         │ HDMI        │   mini-PC)              │      - MQTT broker
         │             └──────────┬──────────────┘    │ - Roku media HTTP       │
         │                        │                     - QX-18 PA mic capture
         │                        │ HDMI                │ - USB FM transmitter    │
         │                        │ (game console)        - 2 × USB audio capture
         │                        │                     │   (TV + rear-radio in)  │
         │                        │                     └ ─ ─ ─ ─┬ ─ ─ ─ ─ ─ ─ ─ ┘
         │                        │                              │ HDMI (cabin UI
         │                        │                              │  + dashboard)
         ▼                        ▼                              ▼
   ┌────────────────────┐
   │ HDMI input         │◀ (all three HDMI sources feed here)
   │ selector (manual)  │
   │ selector (manual)  │
   └─────────┬──────────┘
             │ HDMI
             ▼
   ┌────────────────────────┐
   │ Pyle TV (w/ DVD)       │
   └────────────────────────┘
             ▲
             │ HDMI (via selector)
             │
   ┌────────────────────────┐
   │ AGPtek mini 1080       │
   │ (USB / SD player)      │
   └────────────────────────┘

   Separate today — driving-mode candidate (see subsystems/media/):
   ┌─────────────────────────────────────────────────────────┐
   │ 9" TFT 4-camera backup-cam head unit                    │
   │ RCA composite out → (future USB capture into Pi)        │
   │ → published to LAN → Roku channel `LiveGroup` tile      │
   │ + GPS overlay from Pi gpsd                              │
   └─────────────────────────────────────────────────────────┘
```

## Notes

- The Pi↔router **serial** link is *not wired yet* — no USB-RS232 adapter is present; the Pi's GPIO UART (`/dev/serial0`, PL011) is now enabled and ready (see `subsystems/network/router-serial-uart.md`). Earlier plan was "console override" — that won't work (router RS232 is a DTU). Pi controls the router over SSH/UCI instead; serial is only for the DTU data path.
- Cell booster is acoustically/electrically separate from the router — it boosts the carrier RF before it reaches the router's modem. Mounting rule of thumb: outside antenna in front, inside antenna behind, with enough physical separation to avoid oscillation.
- HDMI selector is manual today. The **SallyNet channel** on the Roku (Phase 0 built; media playback lands in Phase 1) will subsume most of what the AGPtek does, reducing how often the selector needs to be touched.
- The backup-cam head is its own world right now (composite display up front). The driving-mode plan in `subsystems/media/` routes its RCA out through a composite-capture dongle on the mini-PC and re-publishes it as an MJPEG/HLS stream the Roku channel can consume — overlaid with a GPS map panel from the mini-PC's gpsd.
- **Mini-PC plus three new audio paths** are coming with v0.2.0:
  - Snapcast over the QX210's WiFi LAN to phones (each phone runs the Snapcast app; phone's BT pairs to user's headphones)
  - BT A2DP from the mini-PC to one of four owned BT party speakers (speakers do their own TWS stereo pairing to siblings)
  - USB FM transmitter on the mini-PC, BETS-1 compliant (< 1 µW EIRP) — for cabin radio + nearby boat radio + cheap FM earbuds. Not a voice channel.
- **Camper-to-camper voice** is a separate problem with its own answer (amateur 2 m/70 cm mobile), documented in [`subsystems/comms/amateur-radio-path.md`](../subsystems/comms/amateur-radio-path.md). Not part of this network diagram — different RF universe.
