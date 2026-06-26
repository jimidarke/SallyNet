# configs/audio/

Config templates for the audio subsystem. Filled in during Phase 1+ implementation; until then these are stubs.

| File | What it'll hold |
|---|---|
| `snapserver.conf` | snapserver streams + groups (MPD FIFO, librespot FIFO, USB-capture ALSA sources, FM-out sink) |
| `mpd.conf` | MPD pointing at `/var/lib/mpd/music` (the migrated 500 GB HDD), FIFO output for snapserver |
| `librespot.toml` | Spotify Connect device name "Sally", bitrate, FIFO output |
| `pipewire/` | PipeWire routing rules — node names, BT codec preferences (force SBC if SCO/A2DP autoswitch misbehaves), monitor/loopback for PA ducking |
| `pinpad-audio-bindings.yaml` | Cabin pinpad key → action map (source select, volume, BT switch, FM toggle). PTT is **not** here — it lives on the QX-18 (see `subsystems/audio/pa-mode.md`). |

Each file gets created when the corresponding service is first stood up. Keep these in version control once filled — the mini-PC is a single point of failure for audio and these are the recovery artifacts.
