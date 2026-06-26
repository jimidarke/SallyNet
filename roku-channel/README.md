# SallyNet — Roku channel

The in‑rig "glass dashboard" for **Sally** (1985 Ford E‑350 Okanagan motorhome),
sideloaded onto the cabin Roku ("Camperoku"). Pure display: it polls the Pi's
`sally-api` over WiFi and renders SceneGraph — no GPS, no sensors, no data entry on the
TV. Named **SallyNet** to match the WiFi SSID.

Forked from `rokuApp` (HouseWall — state router, `LiveGroup`/`GridGroup`/overlay,
deploy/test toolchain) and `delta/mediaApps/deltaCamRoku` (Task‑based fetch loop +
watchdog/backoff). Part of the **sallyNet monorepo**; backend contract at `../subsystems/media/api-contract.md`.

## Layout
```
images/                 # source art (mascot) — NOT shipped in the .pkg
channel/                # the Roku project (sideload root)
  manifest  bsconfig.json  package.json
  source/    main.brs · Config.brs (palette/registry/log) · Api.brs (URL builders)
  components/
    MainScene.{xml,brs}        # route stack + modeController + poll owner
    screens/  SplashScreen · HomeHub · DriveScreen   (+ Camp/Media/Cameras/Systems/Photos later)
    widgets/  NavTile
    tasks/    StatePollTask     # GET /api/state -> field
  scripts/   deploy.js · generate_brand_assets.py
```

## Build / deploy
```bash
cd channel
npm install
npm run lint                 # bsc --noEmit (no device needed)
python3 scripts/generate_brand_assets.py    # emit icons/splash/mascot from ../images/mascot_orig.png
set -a && . ../.env && set +a
npm run deploy              # roku-deploy sideload to $ROKU_IP (Camperoku must be ON + dev mode enabled)
```

## Runtime config
- Default API base is `SN_API_BASE_DEFAULT()` in `source/Config.brs`
  (`http://192.168.2.216:8090`). Override on‑device without rebuilding via ECP deep‑link:
  `curl -d '' "http://192.168.2.227:8060/input?apiBase=http://10.66.12.216:8090"`.
- Home‑base anchor + thresholds: see `Config.brs`.
