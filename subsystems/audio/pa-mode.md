# PA Mode — QX-18 Handheld + Ducking

Mode 4 of the audio system: a CB-style handheld mic on a hook in the cabin. Lift it, press the button, talk — your voice ducks the music on every output path (Snapcast, BT speaker, FM transmitter) and routes to all of them. Release: music undocks.

## Hardware: QX-18 USB handheld speaker mic

Marketed for Euro Truck Simulator 2 ("Eurotrucker mic") but it's a genuine USB CB-style handheld with a real PTT button, real mic, and a small confidence speaker. ~$60 CAD.

To Linux, the QX-18 appears as **two devices on one USB cable**:

1. **USB Audio Class device** — mic input + speaker output
2. **USB HID keyboard** — the PTT button emits a configurable keycode

Both interfaces are standard UAC + HID. No drivers required on Ubuntu. Comes with a mic holder for cabin mounting.

## Why this beats wiring PTT to the pinpad

- Dedicated physical mic-on-a-hook is the right ergonomic — pull it down, key it, talk. You don't reach for a keypad button to do PA.
- Pinpad stays focused on telemetry log entry + audio source switching (its actual job)
- Confidence speaker built into the QX-18 lets the talker hear themselves come back through the system — instant "is it on?" feedback without staring at a screen

## Wiring + mounting

- USB cable runs from QX-18 to the mini-PC (~6 ft stock, extend with a USB extension if needed; keep total under 5 m)
- Mic holder mounts on the passenger-side dash or the wall between cabin and cab — reachable by anyone in the cabin without unbelting the driver
- USB cable should be strain-relieved at the holder so the cord doesn't pull on the mini-PC port

## Software — PTT capture + ducking

A small Python service (`pa-duck.py`) on the mini-PC:

1. **Identifies the QX-18 HID interface** by USB vendor/product ID — write these into [`configs/audio/pinpad-audio-bindings.yaml`](../../configs/audio/) once known
2. Uses `python-evdev` to grab the keyboard interface (so the PTT keycode doesn't end up in any open terminal) and watches for the configured keycode
3. On key-down:
   - Sends a snapserver JSON-RPC command setting the main music stream's volume to 20% (configurable)
   - Routes `pa-mic` (the QX-18's mic input via PipeWire) into the active snapcast group, ducking-priority
   - Starts the confidence-monitor loopback: a copy of `pa-mic` at low volume to the QX-18's own speaker output (so the talker hears themselves)
4. On key-up:
   - Stops the mic routing
   - Restores main stream volume to its previous level
   - Stops the confidence-monitor loopback

## Latency budget

| Hop | Latency |
|---|---|
| QX-18 mic → mini-PC USB | ~5 ms |
| PipeWire processing | ~10–20 ms |
| Snapcast distribution to phones | ~100 ms (matches music sync) |
| Snapcast → BT speaker via host A2DP | +150–250 ms |
| Snapcast → FM transmitter | ~5 ms |

End-to-end, listeners hear the talker within ~200 ms (FM, phones) to ~400 ms (BT speaker). Acceptable for PA — not for jamming live music.

## Boundary cases

- **What if PTT is pressed when there's no music?** Same flow: just no music to duck. PA mic still goes to all sinks.
- **What if Snapcast is offline?** PA still works to whatever sinks are still up (the FM transmitter is a direct local sink, doesn't need snapserver). Document this as a deliberate feature.
- **Latency on the confidence speaker?** That's the talker hearing themselves come back via the loop ~200 ms later. This is normal and helpful — verifies the system is live. If it's distracting, mute the QX-18 speaker entirely and rely on the cabin BT speaker as the monitor.

## Verification

| Test | Pass criteria |
|---|---|
| QX-18 detected on USB | `lsusb` shows two interfaces (HID + UAC); `arecord -l` shows the mic; `evtest` shows the keycode on PTT press |
| Mic routes when held | Music ducks within 200 ms of press; PA audio is clear on all sinks |
| Music restores on release | Volume returns to previous level within 500 ms |
| Confidence monitor works | Talker hears themselves come back via QX-18 speaker at low volume |
| OS doesn't grab the PTT keycode | `evdev` grab on the QX-18 HID interface prevents the keycode from showing up in terminals / browsers |

## See also

- [`source-switcher.md`](source-switcher.md) — the snapcast group + PipeWire graph this duck-routes into
- [`subsystems/telemetry/`](../telemetry/) — the cabin pinpad (separate device, separate role)
