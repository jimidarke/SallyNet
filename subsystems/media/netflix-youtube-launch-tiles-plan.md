# Plan: Netflix / YouTube launch tiles on the SallyNet Home hub

> Status: **planned, not implemented** (2026-06-27). Scope confirmed: launch-the-app only
> (no content deep-linking yet), tiles for **Netflix** + **YouTube**.

## Why

The "single unified experience" goal still has a gap: no way to jump to the big streaming apps
from the Home hub. `mastertodo.md` and `subsystems/media/README.md` roadmap #5 both call for
Netflix / YouTube tiles on Home.

## The finding that reshapes the original idea

The todo assumed the channel would call ECP `/launch/<id>` itself. **That is not possible:**

- Roku **prohibits a channel from issuing ECP commands** ("Support for sending ECP commands from
  within a Roku app has been discontinued") — enforced by static analysis at publish *and* at
  runtime on OS 14+ (Camperoku is on OS 15.2.4).
- There is **no public in-channel BrightScript API** to launch another channel. `roAppManager` is
  read-only; `roChannelStore` is purchases-only.
- The **only** sanctioned path is an **external controller** issuing the ECP `/launch`. This project
  already has one: the Pi's `sally-api`.

Sources: developer.roku.com External Control API + Deep Linking docs; corroborated by the local
`RokuAppDev` skill (files 04 + 08).

So the launch routes through `sally-api`, which keeps the **"Roku is glass"** rule intact
(`api-contract.md`, `roku-channel/CLAUDE.md`): the channel makes a normal HTTP POST to its backend;
the Pi — as an external controller of its own Roku on the LAN — performs the ECP launch.

## Flow

```
[NavTile "Netflix"] --OK--> HomeHub emits route "launch:netflix"
   -> MainScene onHomeSelect sees "launch:" prefix
   -> LaunchTask POSTs http://<apiBase>/api/launch  (body app=netflix)   [normal HTTP, NOT ECP]
   -> sally-api: roku_ip = request.remote_addr (the Roku that called); appId = map["netflix"] = 12
       -> GET  http://<roku_ip>:8060/query/apps     (verify installed)
       -> if installed: POST http://<roku_ip>:8060/launch/12  -> {ok:true}; Roku switches to Netflix
       -> if not:        -> {ok:false, reason:"not_installed"}  (Roku stays on SallyNet)
   -> on {ok:false}, MainScene shows a toast ("Netflix isn't installed")
```

Deriving the Roku's IP from `request.remote_addr` (the Roku is the caller) means **zero device-IP
config** and it self-corrects if DHCP moves the Roku. Caveat: only valid for LAN calls from the Roku
itself; a `SALLY_ROKU_ECP_BASE` env override is the fallback. ECP calls use stdlib `urllib.request`
— **no new Python dependency**.

App IDs: **Netflix = 12**, **YouTube = 837**.

## Changes (when implemented)

### Backend — `services/sally-api/`
- **`sallyconf.py`**: add (env-overridable, Pi→N100 safe)
  - `ROKU_APP_IDS = {"netflix": "12", "youtube": "837"}` (parsed from `SALLY_ROKU_APP_IDS` JSON env)
  - `ROKU_ECP_BASE = os.environ.get("SALLY_ROKU_ECP_BASE", "")` (empty = derive from `remote_addr`)
  - `ROKU_ECP_TIMEOUT = float(os.environ.get("SALLY_ROKU_ECP_TIMEOUT", "4"))`
- **`app.py`**: add `@app.route("/api/launch", methods=["POST"])`
  - read `app` (form or query); 400 on unknown app name
  - resolve `roku_base` = `cfg.ROKU_ECP_BASE` or `http://{request.remote_addr}:8060`
  - `urllib` GET `/query/apps`, check the appId is present (substring/regex on the XML — avoids an
    XML-parser dep); if absent → `{"schemaVersion":1,"ok":false,"reason":"not_installed"}`
  - else `urllib` POST `/launch/<appId>` → `{"schemaVersion":1,"ok":true}`
  - wrap ECP I/O in try/except → `{"ok":false,"reason":"unreachable"}` on timeout/refused
  - accept optional `contentId`/`mediaType` passthrough (appended to the launch query) for a future
    deep-link pass — no UI wires it yet
  - add `/api/launch` to the `index()` endpoint list
  - mirrors existing idioms (`cfg.SCHEMA_VERSION`, `jsonify`, query/form reads — cf. `api_upload`)

### Channel — `roku-channel/channel/`
- **`components/screens/HomeHub.brs`** (`defs`): add two enabled tiles after Photos —
  `{ label:"Netflix", route:"launch:netflix", enabled:true }`,
  `{ label:"YouTube", route:"launch:youtube", enabled:true }`. No NavTile/XML change needed
  (text tiles match the current Drive/Media/Photos style). The existing OK handler already forwards
  an enabled tile's `route` verbatim, so `launch:*` rides the current path.
- **`components/MainScene.brs`** `onHomeSelect`: add, alongside the existing `Left(r,6)="toast:"`
  branch, a `Left(r,7)="launch:"` branch → set `m.launch.app = Mid(r,8)` and `m.launch.control="RUN"`.
  In `init()` add `m.launch = m.top.findNode("launch")` + `m.launch.observeField("result","onLaunchResult")`;
  `onLaunchResult` shows a toast when `result.ok=false`. Reuses `showToast` + `slEvent`.
- **`components/MainScene.xml`**: add `<LaunchTask id="launch" />` (sibling of the `poll` task).
- **`components/tasks/LaunchTask.{xml,brs}`** (new): input `app`, output `result`. `roUrlTransfer`
  POST to `snLaunchUrl()` with body `app=<app>`, parse JSON → `result`. Model on `tasks/StatePollTask.brs`
  (same `roUrlTransfer` + Task-thread pattern). Fire-and-forget: on success the Roku is already
  switching away, so the response is best-effort.
- **`source/Api.brs`**: add `snLaunchUrl()` = `snApiBase() + "/api/launch"`.
- No appIds in channel code — the channel sends the symbolic name; the server owns the id map (one
  source of truth, keeps Pi→N100 clean).

### Docs
- **`api-contract.md`**: add `/api/launch | POST | new | {ok, reason?}` to the endpoint table + a
  short "Launch (command)" note (additive per its versioning policy).
- **`subsystems/media/README.md`**: roadmap #5 → approach/done; update "Next action".
- **`mastertodo.md`**: rewrite the Netflix/YouTube line to the orchestrator approach (done).
- **`roku-channel/CLAUDE.md`**: note the new files + that external-app launch goes via `sally-api`,
  never in-channel ECP.

## Verification (no live-device steps until the user opts in)

1. **Channel lint** (no device): `cd roku-channel/channel && npm run lint` (`bsc --noEmit`).
2. **Backend, local, no Roku**: run `python3 services/sally-api/app.py`, then
   - `curl -X POST 'http://localhost:8090/api/launch?app=bogus'` → 400 unknown app
   - `curl -X POST 'http://localhost:8090/api/launch?app=netflix'` → `{ok:false,reason:"unreachable"}`
     (no Roku at 127.0.0.1:8060) — confirms graceful failure + the remote_addr path
   - point `SALLY_ROKU_ECP_BASE` at a tiny local stub serving `/query/apps` + `/launch/12` to
     exercise the installed/launch branches without Camperoku
3. **On-device end-to-end (USER-RUN, when ready):** sideload (`npm run deploy`), open SallyNet on
   Camperoku, press the Netflix tile → Netflix launches; uninstalled-app case shows the toast.
   The only step that touches the live Roku — left to the user.

## Out of scope (deferred)
- Content deep-linking (`contentId`/`mediaType`) — endpoint accepts the params but no UI; revisit
  when live-device testing is permitted (per-service ID formats are undocumented).
- Brand logo tile art (text tiles ship first); add via `generate_brand_assets.py` later if wanted.
- Extra apps (Disney+/Prime/Spotify) — trivial later: one line in `ROKU_APP_IDS` + one HomeHub def.
