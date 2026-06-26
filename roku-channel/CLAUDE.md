# CLAUDE.md — SallyNet Roku channel

Sideloaded SceneGraph channel = the **glass dashboard** for Sally. This is the Roku channel
sub-project of the **sallyNet monorepo**: the Pi backend (`sally-api`) is at
`../services/sally-api/`, the frozen API contract at `../subsystems/media/api-contract.md`,
and the docs/subsystems one level up at `../`.

## Architecture (one rule)
Roku is glass: it polls `sally-api` HTTP (`/api/state`, `/api/discovery`, `/api/map.png`,
`/api/media`) and renders. It never speaks MQTT/gpsd/SQLite. Keeping the API contract
(`sallyNet/subsystems/media/api-contract.md`) stable makes the Pi→N100 backend migration a
registry/`apiBase` change with no channel edits.

## Conventions
- **Toolchain:** BrighterScript 0.69 + roku-deploy 3.12 (same as HouseWall/Delta Cam).
  `npm run lint` = `bsc --noEmit`. Sideload via `npm run deploy` (needs `ROKU_IP`,
  `ROKU_DEV_PASSWORD` from `.env`).
- **No module consts** in BrightScript → expose each as a `function` returning the literal
  (see `Config.brs`, `SN_*`). Registry section `sallynet`; bump `SN_CACHE_VER` on schema change.
- **Structured logs:** `slEvent(name, kv)` emits `[SallyNet] event=<name> k=v` (parsed by
  `tests/smoke`). Never log secrets.
- **Decoder discipline:** the Premiere has ONE H.264 decoder. The router must `stop` the
  active video before showing another screen's video (generalize HouseWall's `enterGrid`).
- **Reuse, don't reinvent:** lift HouseWall `components/{LiveGroup,GridGroup,Hud,OverlayLayer,
  Toast}` verbatim when their phase arrives; reuse Delta Cam's go2rtc stream pattern for cameras.

## Device
- Camperoku: Roku Premiere 3920CA, OS 15.2.4, `192.168.2.227` (`10.66.12.227` over WireGuard).
  Dev mode ON. Dev password: `ROKU_DEV_PASSWORD` in the gitignored `roku-channel/.env`. ECP on `:8060`, debug telnet `:8085`.

## Phases (see sallyNet plan)
P0 shell ✅ → **P1 Media ✅** (RowList rows-as-trips, `VodPlayer` MP4 + trick-play + resume) →
P2 Camp/Systems (sensors via MQTT) → P3 Cameras (go2rtc) → P4 audio status →
**P5 Photos ✅** (slideshow + guest-upload QR; built alongside P1) → P6 router → P7 propane/AC.
New media files: `source/Media.brs`, `components/tasks/MediaListTask`, `components/screens/{MediaScreen,VodPlayer,PhotoGallery,QrScreen}`, `components/widgets/MediaCard`.
