# ESP Sensor Fleet — Conventions + Node Catalog

The single source of truth for Sally's ESP32 sensor + input nodes. Individual subsystems
(`tanks/`, `power/`, `lighting/`, this folder's `README.md`) own the *why* and the wiring detail
for their node; **this doc owns the shared contract** every node obeys — firmware choice, MQTT
topic shape, broker, power, secrets, and how a reading travels from a node to the Roku glass.

The plans for these nodes used to be scattered (a written-but-undeployed cabin node, deep design
in `power/` + `tanks/`, a one-line `C4` stub in `mastertodo.md`, the BOM in the moonshot file). This
consolidates them. MQTT is already running on the Pi and is the agreed substrate for the whole fleet.

## Status

Planning consolidation (2026-06-27). **One node is deployable today** (cabin env — its ESPHome
config already exists); the rest are phased and two are gated on physical checks (tank-material
photo, 12V wiring diagnosis). No new hardware decisions block node #0.

## Conventions — the shared contract every node obeys

- **Firmware: ESPHome by default.** It's what the existing `configs/telemetry/cabin-temp-humidity.yaml`
  already uses — declarative YAML, native MQTT, OTA, `!secret` substitution, and HA auto-discovery
  for free. Reach for custom PlatformIO/Arduino **only** if a node's input UX outgrows ESPHome
  lambdas. In practice the fuel keypad menu is the only real candidate; ESPHome's `http_request` +
  `display` + `binary_sensor` covers even the back-seat ETA node.
- **MQTT topic shape: `sally/telemetry/<area>/…`** — the *deployed* convention (cabin + lte already
  use it). `<area>` is the functional name (`cabin`, `bunk`, `camp`, `tanks`, `power`, `fuel`,
  `backseat`, `hookups`); the ESPHome `name:` is `sally-<area>`. Two payload shapes live under it,
  and the archival logger (`scripts/telemetry-logger.sh`) subscribes to catch both:
  - **ESPHome nodes** publish per-sensor to `sally/telemetry/<area>/sensor/<metric>/state` and
    liveness to `sally/telemetry/<area>/status` (`online`/`offline` birth+will). Caught by the
    logger's `sally/telemetry/+/sensor/#` and `+/status`.
  - **Aggregate-JSON nodes** (custom services, like the LTE monitor) publish one JSON blob to
    `sally/telemetry/<area>/state`. Caught by the logger's `sally/telemetry/+/state`.
  - ⚠️ **Schema lock:** anything published *outside* `sally/telemetry/+/…` (e.g. the `sally/power/…`
    / `sally/tanks/…` drift that crept into some planning notes) silently falls out of the logger's
    subscription and is never archived. Keep every node under `sally/telemetry/<area>/`.
- **Broker host lives in `secrets.yaml`** — `mqtt_broker: 192.168.2.216` today (`mosquitto` on
  `campingpi`, no-auth, on-LAN only). The Pi → N100 migration at Phase 3 is then a **one-line
  secrets edit + re-OTA**, not a per-node hunt. Keep `discovery: true` (harmless; lights up an HA
  bridge for free if one ever lands).
- **Power per node:** mains nodes (cabin, tanks, power, fuel, backseat) run off a **12V → 5V buck +
  TVS / input filtering** — never raw RV 12V (the bus swings 11.5–14.4 V and load-dump transients
  kill ESPs; same recipe as `subsystems/lighting/`). The fireside node is **18650 + deep-sleep**,
  publishing every N minutes; **ESP-NOW → a gateway is the noted upgrade path** if WiFi range to the
  campsite or battery life disappoints.
- **Secrets / security:** commit node YAMLs as **templates** (`!secret` + `REPLACE_WITH_*`
  placeholders, the repo convention); git-ignore the real `secrets.yaml` (WiFi creds, broker host,
  OTA password). The existing cabin yaml is kept fully local today — it should migrate to this
  template+secrets pattern.
- **Sensor-only nodes = WiFi is fine.** They never run BT, so they dodge the single-radio WiFi+BT
  time-slicing that bit the Pi 3B / ESP32 on the Halloween project — that conflict is why audio +
  always-on services move to the N100, not why sensors do.

## Data flow — node to glass

```
ESP32 node ─ MQTT ─► mosquitto (Pi :1883) ─┬─► telemetry-logger.sh ─► daily JSONL  (durable archive)
                                            │
                                            └─► telemetry-collector.py ─► SQLite read-model
                                                                              │ (latest per metric)
                                                                              ▼
                                                                   sally-api  /api/state
                                                                   .env .tanks .power .level .systems
                                                                              │ (HTTP, every 5 s)
                                                                              ▼
                                                          Roku Systems screen  +  back-seat OLED
                                                          (both pure glass: HTTP only, never MQTT)
```

The **collector** (`scripts/telemetry-collector.py`, the missing P2 piece) and the existing
**logger** are siblings on the same broker: the logger is the append-only durable archive for
fuel-economy correlations; the collector is the latest-value read-model the API folds into
`/api/state`. **Roku is glass** — it (and the back-seat OLED) read `/api/state` over HTTP and never
speak MQTT, gpsd, or SQLite. That's what keeps the Pi → N100 move a one-line `SALLY_API_BASE` change.

## Node catalog

| # | Node (`area`) | Sensors / role | FW | Power | Status / gate |
|---|---|---|---|---|---|
| 0 | **cabin-env** (`cabin`, dev `sally-01`) | DHT22 now → +BME280/AHT20, DS18B20 engine bay, MPU-9250 IMU (level + heading) | ESPHome | buck | **Config exists — DEPLOY FIRST** (no new HW) |
| 1 | **env satellites** (`bunk`, …) | temp / humidity (clone of #0) | ESPHome | buck | New; "a few spots" |
| 2 | **fireside-portable** (`camp`) | temp + humidity only, deep-sleep | ESPHome | 18650 | **NEW** |
| 3 | **tanks** (`tanks`) | CD4051 mux + reused 1980s probes → fresh/grey/black %; **fresh-fill = level trend** | ESPHome (mux lambda) | buck | Gated: **tank-material photo** |
| 4 | **power** (`power`) | Tier-1 INA228 shunt (SoC) + Tier-2 hall clamps ⇒ **also pump/furnace run-state + shore AC-presence** | ESPHome | buck | Gated: **wiring diagnosis**; propane-safe |
| 5 | **fuel-keypad** (`fuel`) | 4×4 keypad + OLED @ driver door → `POST /api/fuel-log` | ESPHome / custom | buck | Documented (web `/fuel` built) |
| 6 | **backseat-eta** (`backseat`) | button + OLED; on press, GET `/api/state` → show ETA / km-to-dest | ESPHome (`http_request`+`display`) / custom | buck | **NEW** |
| 7 | **city-water switch** (optional) | inline pressure switch on city-water inlet → `systems.city_water` | ESPHome | buck/derive | NEW, tiny; can fold into #3/#4 |

### How the three new ideas map (so the fleet doesn't sprawl)

The genuinely-new asks from the 2026-06-27 session were a portable fireside node, back-seat buttons,
and machine-state sensing. Most of "machine state" folds into nodes that already exist:

- **"Are we there yet?" ETA** → node **#6** only. It's a *consumer* of the existing `trip.eta` /
  `trip.km_to_dest` fields — no new sensors, no contract change. (The session scoped the back-seat
  buttons to ETA only — no call/scene/audio buttons.)
- **Fireside / tent temp+humidity** → node **#2** only. Scoped to temp+humidity, deep-sleep, max
  battery life — no pressure / ping / extras.
- **Appliance run-state** (pump, furnace fan) → **derived from node #4's Tier-2 hall clamps**
  (branch current over a threshold = "running"), optionally a furnace-duct thermistor. **No gas or
  plumbing contact** — propane stays hands-off; the furnace is sensed by heat/current, never its
  lines. Fridge was dropped (the RM763 is broken / storage-only).
- **Hookups** → shore = node **#4** (AC-presence input); fresh-fill = node **#3** (rising level
  trend); city water = node **#7** (a pressure switch), the only net-new hardware here.

So: **two standalone new nodes** (#2 fireside, #6 back-seat) + **one optional tiny switch** (#7).
Everything else rides existing planned nodes.

## Topic → `/api/state` mapping

The collector maps node topics to the frozen API contract (`subsystems/media/api-contract.md`).
`env` stays **flat** for the Roku tile — the collector keeps every per-node value in SQLite for
logging/Grafana, but only the canonical few surface in the API:

| MQTT topic (ESPHome `…/sensor/<m>/state`) | `/api/state` field | Notes |
|---|---|---|
| `sally/telemetry/cabin/sensor/temperature` | `env.in_c` | canonical inside temp |
| `sally/telemetry/cabin/sensor/humidity` | `env.humidity` | |
| `sally/telemetry/cabin/sensor/pressure` | `env.pressure_hpa` | BME280 |
| `sally/telemetry/cabin/sensor/engine_temp` | `env.engine_c` | DS18B20 in the bay |
| `sally/telemetry/cabin/sensor/{pitch,roll}` | `level.{pitch_deg,roll_deg}` | MPU-9250 → `level_ok` derived |
| `sally/telemetry/bunk/sensor/{temperature,humidity}` | SQLite only | not in flat `env` |
| `sally/telemetry/camp/sensor/{temperature,humidity}` | SQLite only (opt. own tile) | fireside; doesn't overwrite `out_c` |
| `sally/telemetry/tanks/sensor/{fresh,grey,black}_pct` | `tanks.{fresh,grey,black}_pct` | |
| `sally/telemetry/power/sensor/{batt_v,batt_a,soc_pct,tte_h}` | `power.{batt_v,batt_a,soc_pct,tte_h}` | Tier-1 shunt |
| `sally/telemetry/power/sensor/shore` | `power.shore` | AC-presence (already in contract) |
| `sally/telemetry/power/sensor/{pump_a,furnace_a}` | `systems.{pump,furnace}` | Tier-2; threshold → bool |
| `sally/telemetry/hookups/sensor/city_water` | `systems.city_water` | optional pressure switch |

**API contract impact:** the v1 shape already reserves `env`/`tanks`/`power`/`level`, so the fleet
needs almost no contract change. The one addition is a small **`systems {pump, furnace, city_water}`**
block (booleans, omit-not-null) — additive, no `schemaVersion` bump. Documented in the contract.

## Build order (with physical gates)

0. **Deploy `sally-01`** (cabin DHT22) — config already written; proves MQTT → logger end-to-end
   with zero new hardware decisions. Fastest possible win.
1. **Stand up the collector** + fold `env` into `/api/state` + light the Roku Systems env tile —
   first telemetry visible end-to-end.
2. **env satellites + fireside node** — clone the cabin pattern; fireside introduces the
   battery/deep-sleep pattern.
3. **Tank node** — *gated on photographing the under-floor tanks* (material → probe-reuse vs SeeLevel).
   Adds `tanks` + fresh-fill trend.
4. **Power node** — *gated on the multimeter wiring baseline* (`vcgencmd get_throttled` must read
   `0x0`). Tier-1 shunt (SoC) first, then Tier-2 hall clamps — which unlock pump/furnace run-state
   + shore presence.
5. **Fuel keypad + back-seat ETA** — the two human-input nodes; build once the sensor spine is solid.
6. **(optional) city-water pressure switch.**

## Decisions locked (2026-06-27)

- Firmware = **ESPHome by default**, custom only where input UX outgrows it.
- MQTT = **`sally/telemetry/<area>/…`**, broker host in `secrets.yaml`; retire the `sally/<subsystem>/…` drift.
- Back-seat input = **"are we there yet?" ETA only**.
- Fireside node = **temp+humidity only**, deep-sleep, battery-optimized.
- Machine-state = **appliance run-state (pump, furnace) + hookups (shore, city water, fresh-fill)**;
  not openings, not deployables; fridge dropped. Most of it **derives from the power & tank nodes**.
- API gains one additive **`systems`** block; everything else fits the frozen v1 contract.

## Cross-references

- `subsystems/telemetry/README.md` — fuel-economy goal + BLE wheel + collector pipeline + cabin UI.
- `subsystems/tanks/README.md` — tank probe-reuse decision (node #3) + propane (Mopeka, read-only).
- `subsystems/power/README.md` + `power/dc-monitoring-brainstorm.md` — the two-tier shunt+hall design (node #4).
- `subsystems/lighting/README.md` — WLED ESP32 nodes (same buck/level-shifter/12V recipe, own subsystem).
- `subsystems/media/api-contract.md` — the frozen `/api/state` surface the Roku reads.
- `subsystems/compute/README.md` — why the broker + collector land on the N100 at Phase 3.

## Next action

Deploy node #0: flash the existing `configs/telemetry/cabin-temp-humidity.yaml` to `sally-01`,
confirm `sally/telemetry/cabin/status` reads `online` on the broker, and watch the first
`temperature`/`humidity` values land in today's `telemetry-logger.sh` JSONL — that proves the whole
MQTT spine before any new hardware is bought.
