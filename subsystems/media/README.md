# Media

**Pyle TV** (with built-in DVD) → manual HDMI input selector → {Roku, **AGPtek mini 1080** media player, (future) Pi}. The **9" TFT 4-camera backup-cam head unit** is separate today (its own display + RCA composite video out). Goal: collapse the Roku + AGPtek into a single unified experience by sideloading a custom Roku channel, AND route the backup-cam feed in too so the rear-view + side cameras can be watched on the big TV while driving.

## Status

- **Working:** Pyle TV + DVD, Roku (Netflix etc.), AGPtek mini 1080 for local files (downloaded movies, family photos). All hang off the manual HDMI switcher.
- **Working separately:** 4-camera 9" TFT backup-cam head — sits up front on its own screen; RCA composite output is currently unused.
- **Pain point:** Multiple devices, multiple remotes, multiple input selections, no continuity. Hard to hand to a kid or a guest. And the rear/side cameras are stuck on a tiny 9" screen.

## SallyNet channel — forked from HouseWall · **Phase 0 BUILT (2026-06-26)**

> The channel now lives in this monorepo at **`roku-channel/`** (app name
> **SallyNet**, matching the SSID). It's sideloaded + verified on Camperoku, polling
> `sally-api` `/api/state` and auto-routing Splash→Home→Drive. The **backend is `sally-api`
> on the Pi today** (`:8090`); it moves to the N100 at Phase 3 and the Roku just repoints
> `SALLY_API_BASE` (no channel code change). The fork notes below are the original plan,
> now largely realized.

Reference: sibling project `~/code/rokuApp` (HouseWall — production sideloaded SceneGraph channel, v0.5, devPassword: `HOUSEWALL_ROKU_DEV_PASSWORD` in the gitignored `.env`).

What to reuse:
- SceneGraph state router (MainScene)
- `LiveGroup` HLS / RTSP / MJPEG playback path with watchdog + exponential-backoff reconnect
- `GridGroup` 2×2 mosaic — repurpose as a scrolling thumbnail grid for movies / photos
- Overlay layer (PIP, text, weather, sensor zones)
- Registry caching pattern for fast cold-start

What to change (~200–300 LOC per the rokuApp explore):
- Replace `DiscoveryTask` (SSDP) with fixed mini-PC IP / mDNS (`sally.local`)
- **Mini-PC** (not Pi — see `subsystems/compute/` for the v0.2.0 host decision) exposes `GET /api/media?type=movies|photos` → JSON manifest + file URLs
- Point `LiveGroup` source at the mini-PC's file URLs instead of camera streams
- Add Netflix / YouTube deep-link tiles via ECP `/launch/<channelId>?contentId=…`

Code lives in a **separate forked repo**, not in this folder. This folder only holds:
- Deploy notes (sideload IP, dev password reminder, build/test cheatsheet)
- Channel config exports
- Screenshots / UX notes

## Bonus idea: live backup-cam → Roku with GPS map overlay (rolling)

This is the fun one. While driving, the big TV in the back of the camper shows:
- A live tile from the 4-camera backup-cam head (rear + side cameras)
- A GPS map overlay (route, speed, ETA) using the planned Pi GPS receiver
- Optional swap-to-fullscreen for any single camera

Implementation sketch:
1. Grab the **RCA composite out** of the 9" 4-cam head unit into a cheap **USB composite video capture dongle** plugged into the **mini-PC**
2. Mini-PC runs `ffmpeg` / `mediamtx` to publish the capture as an **MJPEG or low-latency HLS** stream on the LAN
3. SallyNet channel (forked from HouseWall — `LiveGroup` already speaks HLS/RTSP/MJPEG with watchdog + reconnect) consumes that stream
4. GPS overlay: mini-PC reads `gpsd` (see `subsystems/gps/`), composites a small map + speed/ETA panel into a separate stream, or sends GPS as JSON for the Roku to render natively in a SceneGraph layer (cheaper than re-encoding video)
5. Latency goal: <1.5s end-to-end — composite-capture + MJPEG over LAN is realistic here; HLS adds 4–10s and is too slow for "is the kid still behind me" use

Caveats:
- **Composite video out is interlaced 480i NTSC** — quality will be modest, but for situational rear-view it's fine
- The HouseWall `LiveGroup` reconnect/watchdog logic carries over directly — bumpy roads on RCA = signal loss is real
- The Roku and the backup cam are independent power domains; the Roku must boot fast enough to be useful — keep the channel as the boot-time default (Roku registry pattern, already in HouseWall)

## Roadmap

1. ✅ Forked rokuApp into `sallyNet-channel` (separate repo); rebranded **SallyNet** (sunset palette + mascot).
2. Stand up the **mini-PC** media HTTP service (cross-link: `subsystems/compute/` for the host decision).
3. Strip HouseWall's camera-specific overlays; replace with movie metadata + photo gallery views for the VOD path.
4. ✅ First sideload to Camperoku — verified live (polls `/api/state`, auto-routes Splash→Home→Drive).
5. Add deep-link tile for Netflix.
6. **Driving mode** — composite-capture the backup-cam head into the mini-PC → LAN stream → Roku channel `LiveGroup` tile + GPS overlay.
7. Retire (or relegate) the AGPtek mini 1080 once the SallyNet channel handles local files cleanly (Phase 1).

## Next action

Phase 1 (Media): build `sally-api` `/api/media` (encode-once H.264 MP4 + faststart over HTTP Range) and the SallyNet **Media** screen; retire MiniDLNA for the Roku path; add Netflix/YouTube ECP deep-link tiles.
