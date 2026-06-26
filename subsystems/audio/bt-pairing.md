# BT Speaker Pairing

Four Bluetooth speakers, all owned, all support in-speaker stereo pairing (TWS). Default allocation: **two TWS pairs, two zones** — a fixed cabin pair and a portable pair that travels to wherever the camping is happening (picnic table, campfire, boat). The host only ever pairs to **one** as the A2DP entry point; the speaker handles its sibling on its own via TWS.

## Two zones, three operating modes

| Mode | When | How |
|---|---|---|
| **Single-zone** (default) | One area at a time — cabin OR campfire | Mini-PC switches its A2DP target between the cabin primary and the portable primary. Simple. `audio-bt-switch cabin\|camp\|off`. |
| **Multi-zone simultaneous** | Cabin music AND campfire music at the same time, in sync | Mini-PC drives cabin pair directly; a **second Snapcast client** (an old phone, Pi Zero 2 W with USB BT, etc.) drives the portable pair. Both zones synced sub-100 ms via Snapcast. See diagram in [`source-switcher.md`](source-switcher.md). |
| **Big party / one big zone** | Everyone gathered in one place; want bigger sound | Bring the cabin pair outside. Either both TWS pairs play the same source via Snapcast bridge (above), OR if your speakers support 4-way party-chain (some JBL Connect+, some Bose) chain all four to a single primary. Worth checking your speaker docs. |

## Speaker inventory

> Fill in MAC + model when each is paired for the first time. Use `bluetoothctl scan on` or the speaker's app to find the MAC. **`-primary` is the speaker the host (or Snapcast client) actually pairs to; the sibling joins via in-speaker TWS.**

| ID | Model | MAC | Role | TWS partner | Notes |
|---|---|---|---|---|---|
| `cabin-primary` | TBD | `XX:XX:XX:XX:XX:XX` | Cabin (left or right by orientation) | `cabin-sibling` | The one the mini-PC pairs to |
| `cabin-sibling` | TBD | `XX:XX:XX:XX:XX:XX` | Cabin (other channel) | `cabin-primary` | Joins automatically via TWS |
| `camp-primary` | TBD | `XX:XX:XX:XX:XX:XX` | Portable (campfire / picnic / boat) | `camp-sibling` | The one the Snapcast-client device pairs to in multi-zone mode |
| `camp-sibling` | TBD | `XX:XX:XX:XX:XX:XX` | Portable (other channel) | `camp-primary` | Joins automatically via TWS |

## Pairing flow

1. Pair each speaker to the mini-PC once via `bluetoothctl` — capture the MAC into the table above
2. Mark all four as **trusted** so they auto-reconnect:
   ```
   bluetoothctl trust XX:XX:XX:XX:XX:XX
   ```
3. The host only ever has **one** active A2DP sink at a time. Switching speakers = disconnect current, connect target. The target speaker then chains its TWS partner internally.

## `audio-bt-switch` helper

A small bash helper in [`/sallyNet/scripts/`](../../scripts/) (to be written in Phase 6):

```bash
audio-bt-switch cabin    # → connects cabin-l (cabin-r chains via TWS)
audio-bt-switch camp     # → disconnects cabin-l, connects camp-l
audio-bt-switch off      # → disconnects current A2DP sink
audio-bt-switch status   # → prints currently-connected sink
```

Under the hood: `bluetoothctl disconnect <current> && bluetoothctl connect <target>`, then verify with `pw-cli list-objects | grep bluez`.

This becomes a key binding on the cabin pinpad (e.g. `7` cycles between cabin / camp / off).

## TWS pairing between siblings

Each pair handles its own stereo handshake. The procedure depends on the speaker brand — document per model when discovered:

| Pair | TWS pairing procedure |
|---|---|
| `cabin-l` ↔ `cabin-r` | (TBD — e.g. "hold power on both for 5s, double-tap Bluetooth on left") |
| `camp-l` ↔ `camp-r` | (TBD) |

Once a pair is TWS-bonded, they re-pair to each other automatically when both are powered on — even after months apart. The host only sees one of the two (the "primary").

## Failure modes & recovery

| Symptom | Likely cause | Fix |
|---|---|---|
| Speaker shows in scan but won't connect | Already paired to a phone | Power-cycle the speaker; remove from phone's BT list |
| Audio plays on primary but secondary stays silent | TWS bond broken | Re-pair siblings per model procedure |
| Distorted / crackling audio | A2DP codec mismatch | Force SBC in PipeWire BT config — see [`configs/audio/pipewire/`](../../configs/audio/pipewire/) |
| Host loses BT connection mid-trip | BT range exceeded (host's BT adapter is in the dash area, speakers are 20+ ft away in cabin) | External USB BT adapter at the back of the mini-PC, or move the speaker closer |

## Why the host only pairs to one at a time

Standard BT A2DP is point-to-point. Linux can theoretically pair multiple A2DP sinks via PipeWire combined sinks, but sync between independent BT sinks drifts badly (~50–200 ms between two speakers) — incompatible with the in-cabin stereo experience and causes obvious echo if both pairs are within earshot. Letting the speakers handle their own TWS pairing per-zone, and using **Snapcast** (over WiFi) for cross-zone sync, is the right answer.

## Boat scenario (Snapcast over WiFi extender)

The boat does not use FM — it uses Snapcast. Topology:

1. A phone, tablet, or small Pi in the boat runs the Snapcast client app, joined to Sally's WiFi LAN
2. That device's BT pairs to one of the portable speakers (or a separate waterproof BT speaker you bring along)
3. Audio stays in sync with whatever's playing in Sally's cabin / at the campfire

The constraint is WiFi reach. **The QX210 has external/swappable WiFi antennas, so a 6 dBi omni upgrade ($30–60 for both) is the expected first fix** — see [`subsystems/network/`](../network/) Step 1. That alone should bring boat-class distances into range; if not, fall back to a USB-powered portable repeater **in bridge/transparent mode** (default "create-a-new-network" mode breaks Snapcast L2 discovery).

## See also

- [`source-switcher.md`](source-switcher.md) — how the BT sink fits into the snapcast graph
- [`README.md`](README.md) — Mode 2 (highway-shared) + Mode 3 (camp / boat)
