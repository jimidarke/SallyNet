# sally-api

The single HTTP surface the Roku dashboard polls (see
[`subsystems/media/api-contract.md`](../../subsystems/media/api-contract.md) for the frozen
schema). Runs on **`:8090`** so it never collides with the existing `:80` metrics app.

## Files
- `app.py` — Flask app: `/api/state`, `/api/discovery`, `/api/health`, `/`.
- `gpsd_client.py` — dependency-free gpsd JSON-socket reader.
- `sallyconf.py` — env-overridable config (port, gpsd, home anchor, thresholds).

## Run locally
```bash
SALLY_API_PORT=8090 python3 app.py
curl -s localhost:8090/api/state | jq
```

## Deploy to the Pi
```bash
scripts/deploy-sally-api.sh          # rsync → /opt/sally/sally-api, install+start systemd unit
curl -s http://192.168.2.216:8090/api/state | jq      # on SallyNet
curl -s http://10.66.12.216:8090/api/state | jq       # over the WireGuard link
```

Phase 0 serves live `gps` + `drive.km_from_home`; `power/tanks/env/level/cameras/audio`
are `null` until later phases. Today it runs on `campingpi`; at Phase 3 it moves to the N100
and the Roku just repoints `SALLY_API_BASE` — no code change.
