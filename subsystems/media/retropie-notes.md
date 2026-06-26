# RetroPie / `campingpi` — Audit & Update Plan

Notes on Sally's Raspberry Pi 3B+ (`campingpi`), captured 2026-06-25 from a live read-only audit over SSH. This box is the retro-gaming appliance **and** quietly the LAN media/file server. Nothing here has been changed — this is a documented plan to action later.

> Lives in `media/` because the box also serves the DLNA library that the future Roku channel will consume. Host-level details also cross-referenced from `docs/current-state.md` and `subsystems/power/`.

## Host & access

| | |
|---|---|
| Hostname / IP | `campingpi` / **192.168.2.216** (SallyNet, `192.168.2.0/24`) |
| Hardware | Raspberry Pi 3B+ (Rev 1.4, 4-core armv7l, 744 MB usable RAM after 256 MB GPU split; WiFi/BT disabled) |
| OS | Raspbian GNU/Linux 10 (**Buster**), kernel 5.10.103-v7+, image base 2022-01-28 |
| SSH | key-based — `ssh campingpi` (alias in `~/.ssh/config`, user `pi`, key `~/.ssh/sally_campingpi`) |
| Storage | SD: 58 GB (14% used) holds OS + roms + saves. USB HDD: ~1 TB exFAT at `/mnt/usb` holds media |

### Services running (not "pure RetroPie")
- **RetroPie 4.8** (EmulationStation + RetroArch) — roms on the SD card at `/home/pi/RetroPie/roms`
- **Samba** (`:445`) — shares `[roms]`, `[bios]`, `[homes]`
- **MiniDLNA "CampingNetMedia"** (`:8200`) — serves video from the HDD
- **Flask "System Metrics"** (`:80`) — `/home/pi/web/app.py` (psutil host stats), runs as **root**, no auth, started by `web_app.service`

## DLNA media library (`/mnt/usb`)

| Dir | Size | Contents |
|---|---|---|
| `media/movies` | 180 GB | 136 films, mostly `.mp4` (family/Disney/Pixar/Marvel) |
| `media/tv` | 133 GB | 4 shows, mostly `.mkv`: Bluey (154 eps), Family Guy (141), Rick and Morty (72), Wild Kratts (16) |
| `shared` | empty | configured (`PV`) but unused |

- **519 video files total** (~313 GB). Format split: 378 mkv / 141 mp4.
- **Codec sniff:** movies = MP4 (`ftypisom`, H.264/AAC); TV `.mkv` sample = `V_MPEG4/ISO/AVC` (H.264) + `A_AAC` → **Roku direct-playable**. Good news for the channel plan: minimal/no transcoding needed (the Pi couldn't transcode anyway, and has no `ffmpeg`/`mediainfo` installed).
- **No metadata** to speak of (2 `.nfo`, 1 `.jpg` across the library) — a Roku channel gets title strings but no posters/descriptions unless scraped.
- Overlaps the planned mini-PC media-HTTP role (`subsystems/compute/`, `subsystems/media/README.md`) — **reconcile before building new media plumbing**; the Roku could just consume `CampingNetMedia`.

## RetroPie library

| System | Games | System | Games |
|---|---|---|---|
| arcade | 2,543 | gba | 12 |
| nes | 149 | atari2600 | 12 |
| **snes** | **76** | psx | 21 |
| n64 | 18 | nds / music / love / kodi | a few |

SNES standouts present: Chrono Trigger, FF III (=VI), Secret of Mana, Zelda ALttP, Super Mario World, Yoshi's Island, Mario Kart, F-Zero, Star Fox, DKC, Mega Man X, Contra III, TMNT IV, Kirby Super Star, Killer Instinct, MK II / UMK3. Save files (`.srm`) dated Aug 2024 show real play history (DKC, Mario Kart, Mario World).

## ⚠️ Known issue: SNES (and other systems) missing from the ES menu

**Root cause:** `~/.emulationstation/es_settings.cfg` has `ParseGamelistOnly = true`, which makes EmulationStation list **only** games written in each system's `gamelist.xml` instead of scanning the roms folder. The SNES `gamelist.xml` is **0 bytes (empty)** → ES sees zero SNES games → hides the whole SNES system, even though all 76 roms are on disk. Any system with an empty/missing gamelist disappears the same way.

**Fix options:**
1. Set `ParseGamelistOnly` → `false`, then restart EmulationStation (it rebuilds the menu by scanning folders). Simplest, most robust.
2. Populate the gamelists with the scraper (gets box art + metadata too). Nicer, needs internet, heavier.

**⚠️ Caveat — timing matters:** EmulationStation **overwrites `es_settings.cfg` on exit**, so an SSH edit made while ES is running gets wiped. And the menu only rebuilds on an ES restart. So apply the fix **between game sessions**, either:
- In the UI: `Start → Other Settings → "Parse Gamelists Only" → OFF`, then `Start → Quit → Restart EmulationStation`, **or**
- Over SSH: quit ES first, edit `es_settings.cfg`, relaunch ES.

## Config audit vs. best practice (2026)

| Area | Current | Recommendation |
|---|---|---|
| OS | Raspbian Buster (Debian 10) | **EOL** — repo no longer updates. Aging out (see update plan). |
| RetroPie-Setup | 4.7.1-545, commit 2022-03-13 | ~4 yrs stale; project still active. Years of core fixes missed. |
| SNES core | `lr-snes9x2005` | → **`lr-snes9x2010`** for Pi 3B: wider compatibility (special-chip games), still fast. 2005 runs some games too fast. |
| arcade core | `lr-fbneo-neocd` (default) | **Likely wrong** — NeoCD is Neo-Geo *CD*. Generic arcade default should be `lr-fbneo` or `lr-mame2003`. Probably why some arcade roms don't launch. |
| n64 core | `mupen64plus-auto` (standalone) | ✅ Correct for Pi 3B. |
| nes/psx/gba/genesis | fceumm / pcsx-rearmed / mgba / genesis-plus-gx | ✅ Sensible defaults. |
| mame-libretro | `lr-mame2003` | OK; `lr-mame2003-plus` is more compatible (needs matching romset). |
| RA perf | rgui menu, `video_threaded=true`, `rewind=false` | ✅ All correct for a Pi 3B. |
| Shaders | `video_shader_enable=true` (global) | 🔍 Verify no heavy CRT shader loaded — would hurt the 3B. |
| config.txt | gpu_mem 256, **no overclock** | ✅ Keep stock. **Do NOT overclock** until power is fixed. |
| Power | browns out (`get_throttled=0x50000`) | ⚠️ Real stability risk (SD corruption). See `subsystems/power/`. |
| Controllers | 2× generic "USB Gamepad" autoconfig | Works; confirm both pads map correctly per-controller. |

## Update plan — two tiers

"Just update in place" is **not** the clean path: Buster is EOL, so `apt`/RetroPie-Setup updates on it are fragile (archived repos), and RetroPie/Pi community guidance favors a **fresh image over an in-place dist-upgrade** (Buster→Bookworm in place "breaks more than it fixes"). But a reflash is a real migration here because the box is not pure RetroPie.

### Tier 1 — low-risk config fixes (reversible, no OS change)
Do these between game sessions; none touch the OS.
1. Restore SNES visibility (`ParseGamelistOnly=false` or scrape gamelists).
2. Switch SNES default core → `lr-snes9x2010`.
3. Fix the arcade default core (`lr-fbneo` / `lr-mame2003`).
4. Verify the global shader isn't dragging performance.
5. **Power:** fix the 12V→5V converter so it stops browning out — the one item that actually threatens the system. Tracked in `subsystems/power/`.
6. (Optional) clean misfiled SNES junk: `Lemmings - Fun Levels.tap`, and the bootleg/hack carts (Pokemon Stadium Unl, Sonic Unl, SFII Lightning Edition).

### Tier 2 — modernization (plan deliberately, back up first)
- Fresh current image (Bookworm-based RPi OS + reinstall RetroPie via RetroPie-Setup).
- **Migrate, with verified backups:** roms + saves (`.srm`/`.state`, on the SD not the HDD), scraped gamelists/art, RetroArch configs, **and** rebuild the custom layer — Samba shares, MiniDLNA config, Flask metrics service, WiFi/SSH key.
- Only worth the effort for newer cores/features or once Buster breakage bites. Treat as a planned project, not a quick update.

**Pre-req before either tier:** verify `apt` still works on this EOL Buster (deliberately not run during the audit).

## Sources
- [RetroPie SNES core discussion (Pi 3)](https://retropie.org.uk/forum/topic/14639/lr-snes9x-runs-faster-better-than-lr-snes9x2010-stock-pi-3-copper-sinks-latest-software-versions)
- [Updating RetroPie (docs)](https://retropie.org.uk/docs/Updating-RetroPie/)
- [RetroPie download / current version](https://retropie.org.uk/download/)
- [Pi forums — upgrading an old Pi 3](https://forums.raspberrypi.com/viewtopic.php?t=394583)
- [RetroPie-Setup releases](https://github.com/RetroPie/RetroPie-Setup/releases)

## Applied 2026-06-26

Tier 1 config fixes done over the VPN + reboot:
- ✅ `ParseGamelistOnly` → **false** (es_settings.cfg) — SNES (and any bare-gamelist system) now folder-scans and appears.
- ✅ Deleted the **0-byte/corrupt `gamelists/snes/gamelist.xml`** (it was throwing `Error parsing XML`; non-fatal with folder-scan on, but removed for cleanliness).
- ✅ SNES default core → **`lr-snes9x2010`** (was 2005; both installed).
- ✅ arcade default core → **`lr-fbneo`** (was `lr-fbneo-neocd`, the Neo-Geo-CD subsystem — wrong for general arcade).
- All four survived the reboot; ES back up clean. (SNES menu visibility to be eyeball-confirmed on the TV.)

## Next action

Remaining Tier 1: verify no heavy shader is loaded (step 4) and optional rom cleanup (step 6). **Priority is the power/under-voltage fix** (`../power/`) — a fresh-boot reading reconfirmed `0x50000` within **1 minute of boot**, i.e. it browns out during the boot surge. Tier 2 (fresh Bookworm image) still stands; this reboot also reconfirmed the Raspbian Buster repo is dead (`iptables-persistent` 404).
