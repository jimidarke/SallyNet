# sally-api

The single HTTP surface the Roku dashboard polls (see
[`subsystems/media/api-contract.md`](../../subsystems/media/api-contract.md) for the frozen
schema). Runs on **`:8090`** so it never collides with the existing `:80` metrics app.

## Files
- `app.py` — Flask app: all routes (`/api/state`, `/api/media`, `/api/collections/<id>`,
  `/api/show/<id>`, `/media/<path>` Range, `/api/photos`, `/api/upload` + `/upload`,
  `/api/trip` + `/trip`, `/api/fuel-log` + `/fuel`, `/api/waypoints` + `/waypoints`,
  `/api/map.png`, `/map`, `/api/view`, `/api/discovery`, `/api/health`, `/`).
- `sallyconf.py` — env-overridable config (port, gpsd, home anchor, thresholds, tile/TMDB keys).
- `gpsd_client.py` — dependency-free gpsd JSON-socket reader.
- `store.py` — atomic JSON read-model store (flock + `.tmp`+`os.replace`) backing the trip
  store, OSRM route cache, and fuel log.
- `tiles.py` — slippy-tile math + best-effort disk-cached tile fetcher (negative cache +
  circuit breaker for a throttling provider).
- `mapgen.py` — composes the `/api/map.png` frame (basemap + trail + POI + waypoints + status
  strip), single-flight cached.
- `trail.py` — today's GPS breadcrumb polyline for the map's trail layer.
- `waypoints.py` — trip waypoint selection logic ("next" waypoint, countdown, favourites).
- `navstate.py` — pure GPS-loss/fix-age nav-tick logic (shared with `scripts/nav-tick.py`).
- `studio_index.py` — scans `STUDIO_ROOT` (`movies/`, `tv/`) into the Movies/TV read-models.
- `studio_art.py` — TMDB poster/genre match + ffmpeg frame-grab fallback, cached under
  `STUDIO_ROOT/.art/`.
- `studio_reindex.py` — orchestrates scan → art fetch → categorize → atomic `movies.json`/
  `tv.json` write; the glue `scripts/media-index-studio.py` and `scripts/media-fetch-art.py` call.
- `test_*.py` — unittest coverage per module above, runnable off the Pi (`python3 -m unittest`).

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

`gps`/`drive`/media (Trips + Movies/TV studio library)/map/trip/fuel/waypoints are all live
today. Sensor blocks (`power`/`tanks`/`env`/`level`/`systems`/`cameras`/`audio`) are **omitted**
(never `null`) until their phase lands — see `api-contract.md`. Today this runs on `campingpi`;
at Phase 3 it moves to the N100 and the Roku just repoints `SALLY_API_BASE` — no code change.
