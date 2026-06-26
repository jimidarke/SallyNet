# Source Switcher — PipeWire + Snapcast

The heart of Sally's audio. One graph routes any input to all three outputs, with Snapcast keeping clients in sync.

## Inputs

| Source | Hardware path | PipeWire node name (suggested) |
|---|---|---|
| **Local music (MPD)** | Existing 500 GB USB HDD mounted at `/var/lib/mpd/music`. MPD's `httpd` output feeds snapserver via FIFO. | `mpd-out` |
| **Spotify Connect** | `librespot` running headless; advertises Sally as a Spotify device. Output to a FIFO snapserver reads. | `librespot-out` |
| **Pyle TV audio** | 3.5 mm or RCA out from the Pyle → USB audio capture card #1 (Behringer UCA222 or generic CM108 dongle). Appears as `alsa_input.usb-...`. | `tv-cap` |
| **Rear radio audio** | Line-out from the new rear radio → USB audio capture card #2 (or the second channel of a 4-in interface). | `radio-cap` |
| **QX-18 PA mic** | USB Audio Class mic input of the QX-18 handheld. Only routed when PTT is held; ducks the others. See [`pa-mode.md`](pa-mode.md). | `pa-mic` |

## Outputs (snapcast clients, all live simultaneously)

| Sink | How it leaves the mini-PC | Notes |
|---|---|---|
| **Phones in cabin** | snapserver TCP → snapclient app on each phone over Sally's WiFi LAN | Phone's own BT pairs to user's headphones — out of scope for the mini-PC |
| **BT A2DP cabin/camp speaker** | PipeWire BT module → host pairs to one of the 4 owned speakers; speakers stereo-chain to siblings on their own | Pair script in [`bt-pairing.md`](bt-pairing.md) |
| **FM transmitter** | USB FM transmitter as an ALSA sink; snapclient on the mini-PC writes to it | BETS-1 cap, see [`fm-broadcast.md`](fm-broadcast.md) |
| **(Future)** wired ESP32 endpoint | snapclient-esp32 firmware → I2S DAC → amp → speaker | Phase 7 only |

## Source selection

A single "current source" → snapserver group. Switching is destructive (one source at a time, like a real input selector). Bindings on the cabin pinpad (the one already planned for telemetry — see [`subsystems/telemetry/`](../telemetry/)):

| Key | Action |
|---|---|
| `1` | Source = MPD (HDD music) |
| `2` | Source = Spotify Connect (librespot) |
| `3` | Source = Pyle TV capture |
| `4` | Source = Rear radio capture |
| `5` | Mute all outputs |
| `6` | Toggle FM transmitter on/off |
| `7` | Toggle cabin BT speaker on/off |
| `*` | (held) volume down |
| `#` | (held) volume up |

PTT is **not** on the pinpad — it's the dedicated button on the [QX-18 mic](pa-mode.md).

A small Python service watches `evdev` for the pinpad and translates keys → snapserver JSON-RPC commands (snapserver exposes a control API). Same service handles MPD's MPC protocol for source-side track skip.

## Why PipeWire (not PulseAudio)

- PipeWire's BT-A2DP support is now more robust than legacy PulseAudio
- Single graph for both ALSA and BT routing — fewer moving parts
- The combine-sink pattern is cleaner; `pw-loopback` is the building block for the ducking trick in PA mode
- Active default on Ubuntu Server 24.04 LTS

## Sync expectations

- Snapcast clients on phones: sub-100 ms drift, fully sync'd for the same audio across the cabin
- Host's BT A2DP sink: an extra ~150–250 ms latency due to BT codec buffering — snapserver compensates if configured with a per-client delay
- FM transmitter: near-zero added latency (analog modulation on the host's audio output)

If a movie is the source (TV capture → Snapcast), lip-sync may drift by a few hundred ms on BT headphones — that's inherent to BT. Wired ESP32 endpoints (Phase 7) eliminate this for any zone where lip-sync matters.

## Configs

Stubs (to be filled in during Phase 1):
- [`configs/audio/snapserver.conf`](../../configs/audio/) — snapserver streams + groups
- [`configs/audio/mpd.conf`](../../configs/audio/) — MPD pointing at the HDD, output to snapserver FIFO
- [`configs/audio/librespot.toml`](../../configs/audio/) — Spotify Connect device name "Sally"
- [`configs/audio/pipewire/`](../../configs/audio/pipewire/) — routing rules + node names above
- [`configs/audio/pinpad-audio-bindings.yaml`](../../configs/audio/) — key → action map

## Next action

When the mini-PC arrives: install Ubuntu Server 24.04 LTS, enable PipeWire (default), install MPD, prove HDD music plays through the mini-PC's onboard audio. Snapcast, BT, and FM all come after that baseline works.
