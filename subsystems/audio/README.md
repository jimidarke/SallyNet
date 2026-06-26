# Audio

Sally is loud on the highway — the Pyle TV is unhearable above ~80 km/h. Camping wants real sound for the fire pit. Adjacent campsites in the same group want a shared soundtrack on any FM radio. The boat wants Snapcast-quality audio via WiFi (not FM — boat is too far + WiFi gives perfect sync). This subsystem solves all of those from one source, three simultaneous outputs.

## Architecture in one line

**One source switcher on a mini-PC → Snapcast over WiFi to phones → BT A2DP to one of four owned speakers → BETS-1-legal FM broadcast.** All three outputs always live; pick what each listener uses.

```
   ┌─────────────────────────┐
   │  SOURCE SWITCHER (mini-PC) │  PipeWire graph + snapserver
   │  Inputs: TV cap, rear-radio cap, MPD (HDD),
   │          librespot, QX-18 PA mic
   └────────────┬────────────┘
                │
                ▼
        snapcast stream
                │
   ┌────────────┼────────────┐
   ▼            ▼            ▼
 Snapcast    BT A2DP       FM transmitter
 to phones   to TWS pairs  (BETS-1, <1 µW
 + boat      (cabin pair   EIRP — covers Sally
 (over WiFi  + portable    + adjacent sites in
 extender    pair); cross- the camping group +
 if needed)  zone sync via cheap FM handhelds /
             a second      earbuds for the crew)
             snapclient
```

The full design rationale (and why this avoids the ESP32 WiFi/BT radio conflict from the Halloween project) lives in the plan file at `~/.claude/plans/sally-is-the-name-synchronous-cocoa.md`. The four modes (highway-personal / highway-shared / camp / PA) are described there; this README is the index for the implementation-side docs in this folder.

## Files in this subsystem

| File | Purpose |
|---|---|
| [`README.md`](README.md) | This — index + one-line architecture |
| [`source-switcher.md`](source-switcher.md) | PipeWire routing graph, MPD/librespot/USB-capture wiring, source-switch pinpad bindings |
| [`fm-broadcast.md`](fm-broadcast.md) | FM transmitter hardware + the BETS-1 power cap as a hard rule |
| [`pa-mode.md`](pa-mode.md) | QX-18 handheld mic routing, PTT key capture, ducking |
| [`bt-pairing.md`](bt-pairing.md) | MAC inventory of the 4 BT speakers, named pairing scripts |

Configs live in [`/sallyNet/configs/audio/`](../../configs/audio/).

## Dependencies

| On | Why |
|---|---|
| [`subsystems/compute/`](../compute/) | The mini-PC host that runs everything. **Phase 1 of this subsystem requires the mini-PC to land first.** |
| [`subsystems/network/`](../network/) | QX210 must serve a stable WiFi LAN for Snapcast multi-client sync to work |
| [`subsystems/telemetry/`](../telemetry/) | Cabin pinpad doubles as the audio source-switch input (PTT is dedicated to the QX-18 mic, not the pinpad) |
| [`subsystems/comms/`](../comms/) | Crosslink: the camper-to-camper duplex idea is **not** the FM broadcast leg here — that's amateur radio, see `subsystems/comms/amateur-radio-path.md` |

## Status

Planning + parts-list only. Nothing built. Phased roadmap (each phase independently useful) lives in the plan file.

## Next action

Procurement: pick a specific N100 mini-PC (Beelink S12 or GMKtec G3 are the typical contenders), source the 12 V → 19 V **boost converter** (or better: a buck-boost, since Sally's house-battery bus swings ~11.5–14.4 V across charge states), and one USB FM transmitter (USB-line-in C.Crane class is the path of least resistance for Phase 1). Everything else can wait until those land.
