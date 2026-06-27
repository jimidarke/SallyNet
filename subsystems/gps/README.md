# GPS Tracking

GPS receiver on the Pi → `gpsd` → Traccar client → home Traccar server. Lets the family see Sally's location in real-time, and gives a trip history for memory's sake.

## Status

**GPS + gpsd live — verified 2026-06-26.** The receiver plugged into the Pi is a **u-blox 8 GNSS** (UBX-M8030, USB `1546:01a8`), enumerating on `/dev/ttyACM0`. `gpsd 3.17` is installed and configured against the stable by-id path with `-n`, socket-activated (`gpsd.socket` enabled), and **serving a 3D DGPS fix** on `localhost:2947` — verified via `gpspipe` (HDOP ~0.65, ~12 satellites used incl. SBAS PRNs 133/135).

> **Buster-EOL install note:** Raspbian's normal mirror (`raspbian.raspberrypi.org`) now 404s for Buster, so `gpsd` wouldn't install. The Pi's `/etc/apt/sources.list` was repointed to **`legacy.raspbian.org`** (original saved as `sources.list.orig`). This also un-breaks apt for any future package install on `campingpi`.

## Hardware

**Installed (2026-06-26):** a **u-blox 8 G-Mouse** (UBX-M8030) on `/dev/ttyACM0` — newer than the VK-162 (u-blox 7) options scoped below.

| Option | Cost | Notes |
|---|---|---|
| **VK-162 "G-Mouse" USB GPS** | ~$15 | u-blox 7 chipset, NMEA over `/dev/ttyACM0`, magnetic mount. The hobbyist default. |
| GlobalSat BU-353-S4 | ~$40 | Higher-quality classic option if VK-162 underperforms |

## Software stack

- `gpsd` on the Pi listening on `/dev/ttyACM0` → exposes a TCP socket
- **Traccar Client** on the Pi → reports to a Traccar server
- **Traccar server** — check the `homeController` estate for an existing Traccar host; if none, the cheapest path is to add it to `nserver` or run on a small VPS

References:
- [Traccar on Raspberry Pi forum thread](https://www.traccar.org/forums/topic/raspberry-pi-as-a-client-if-anyone-is-interested/)

## Roadmap

1. ✅ GPS receiver in + `gpsd` serving a live 3D fix (2026-06-26).
2. ✅ Exposed to the dashboard — `sally-api` `/api/state` reads gpsd; the SallyNet Roku channel polls it.
3. (optional) Traccar for family location sharing — check the `homeController` estate for an instance, or skip in favour of the in-rig dashboard.

## Mode derivation (4-state, 2026-06-27)

`sally-api` derives an instantaneous **mode** from the GPS fix + the active trip:
`driving` (speed ≥ 10 km/h) → `at_home` (within 1 km of the home anchor) → `camping`
(stopped within 250 m of the **active trip's destination** — set via the `/trip` entry
page) → else `parked`. The Roku auto-routes Home ⇄ Drive ⇄ Camp on this with a short
hysteresis. Thresholds are env-tunable (`SALLY_DRIVING_KMH`, `SALLY_HOME_RADIUS_M`,
`SALLY_DEST_RADIUS_M`). See `subsystems/media/api-contract.md`.

## Next action

gpsd is live and feeds the 4-state mode machine + trip ETA. **Maps/waypoints/POIs is the
next GPS-adjacent push** — needs its own spec (offline OSM tile cache for dead zones;
`/api/map.png` is already reserved). Traccar family location sharing stays a parallel
option (check the `homeController` estate for an existing instance).
