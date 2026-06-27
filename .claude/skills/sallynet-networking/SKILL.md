---
name: sallynet-networking
description: >-
  SallyNet's networking and remote-access reference — how Sally the motorhome's
  rolling LAN is wired and how to reach it. Use for any connectivity or
  remote-access task: the WireGuard/VPN tunnel home, reaching the Pi, router, or
  Roku remotely from the WSL dev box, IP addressing and the LAN schema, the
  QX210-NW2 cellular router and its LuCI web UI, the LTE uplink and its
  signal/bandwidth telemetry, the Pi↔router RS232 link, or which nodes exist and
  are planned. Trigger even without the word "network" — e.g. "I can't reach the
  Pi from home", "bring up the tunnel", "why is streaming choppy", "what's
  Sally's router IP", "is the modem online". For deploying or restarting services
  on the Pi, use sallynet-pi-ops; for the :8090 API and the user-facing web/Roku
  UIs, use sallynet-interfaces.
---

# SallyNet networking

Sally is a 1985 motorhome with a self-contained rolling network: a cellular
router (QX210-NW2) is the gateway, a Raspberry Pi (`campingpi`) hosts the
always-on services, a Roku ("Camperoku") is the TV glass, and ESP32 sensor nodes
join over WiFi. The whole LAN is reachable from home over a **dial-out WireGuard
tunnel** because the cellular uplink sits behind carrier CGNAT.

This skill is a **thin index over the source of truth**. The stable facts you
need fast (IPs, the bring-up command, which endpoint to hit) are inline; for deep
detail follow the links to the canonical repo docs — they own the why and won't
drift out from under you.

## Topology + addressing

LAN `192.168.2.0/24`, SSID **SallyNet**, WAN = `wwan0` (LTE cellular).

| Device | LAN IP | Overlay IP (from home) | Notes |
|---|---|---|---|
| QX210-NW2 router | `192.168.2.1` | `10.66.12.1` | gateway; LuCI on `:80` **only** (no SSH) |
| Pi `campingpi` (3B+) | `192.168.2.216` | `10.66.12.216` | wired `eth0`; WiFi+BT disabled; hosts all services |
| Roku "Camperoku" | `192.168.2.227` | `10.66.12.227` | Premiere 3920CA; ECP on `:8060` |
| ESP32 nodes | DHCP | — | sensor fleet (planned; cabin node ready) |
| Mini-PC (N100) | planned | — | takes always-on services at Phase 3 |

The overlay `10.66.12.0/24` is a 1:1 NETMAP of the real `192.168.2.0/24` (last
octet preserved) — so from home you reach `.216` as `10.66.12.216`. WAN profiles
(cell vs WiFi-as-WAN) live in the router's `/etc/config/network` (UCI).

## Reaching Sally remotely (from the WSL dev box)

Sally's router is behind carrier **CGNAT** (IPv6 + NAT64, no inbound port-forward),
so remote access is a **phone-home** WireGuard site node: `campingpi` dials a hub
at home (`hub.example.net:51820` on DarkeRouter) and bridges the whole LAN in.

Bring the tunnel up from this WSL box (the `.5` client), then SSH the Pi:

```bash
sudo wg-quick up ~/code/homeController/secrets/wg-clients/sally.conf
ssh -i ~/.ssh/sally_campingpi pi@10.66.12.216          # the Pi
sudo wg-quick down ~/code/homeController/secrets/wg-clients/sally.conf   # when done
```

Once the tunnel is up, the rest of the LAN answers at its overlay IP:

```bash
ping 10.66.12.1                 # QX210 router
http://10.66.12.1               # LuCI web UI
curl -s http://10.66.12.216:8090/api/health   # sally-api liveness
ssh -D 1080 10.10.10.12 -N      # SOCKS proxy straight through the site node
```

⚠️ **Bufferbloat gotcha:** when Sally is streaming a movie/tablet, the cellular
link bloats to ~3–4 s RTT and **multi-round-trip `scp`/`rsync` stalls**. Prefer
single-connection transfers (the base64-inline deploy path). This is the #1 cause
of "the deploy hung." See [`sallynet-pi-ops`](../sallynet-pi-ops/SKILL.md).

The tunnel self-heals via `sally-wg-watchdog.timer` on the Pi (every 60 s: boot-race
retry, re-resolve the hub's dynamic DNS, bounce a stale handshake). It only papers
over drops — the real fix for instability is the Pi's 5 V power feed.

Full topology, keys, permitted clients, and every reach-it command:
**[`references/remote-access.md`](references/remote-access.md)**.

## QX210 router — manage over LuCI, never SSH

The QX210-NW2 has **SSH/dropbear disabled** (verified 2026-06-26). Manage it over
**HTTP `:80` (LuCI) only** — any automation must drive the LuCI endpoints, not ssh.
Two JSON endpoints matter (auth + shapes in
[`references/router-luci.md`](references/router-luci.md)):

- `…/admin/status/realtime/bandwidth_status/wwan0` → live byte counters (LTE)
- `…/admin/status/overview?status=1` → modem signal (`dbm`, `rssi`), operator, SIM

The router's **RS232 port is a DTU (data passthrough), not a console** — don't try
to get a shell on it. The Pi's freed UART (`/dev/serial0`) is the side that wires
to it. Details in `subsystems/network/router-serial-uart.md`.

## LTE uplink telemetry (check this first for streaming/uplink issues)

`sally-lte-monitor.service` on the Pi polls the LuCI endpoints every 10 s and
publishes to MQTT (`mosquitto` on `192.168.2.216:1883`, no-auth, LAN-only):

- `sally/telemetry/lte/state` — JSON: `up_bps`, `down_bps`, `signal_dbm`, `rssi_pct`,
  `operator`, `conn_status`, `sim_status`, totals…
- `sally/telemetry/lte/status` — `online`/`offline`

When the user reports choppy streaming, a stalled deploy, or "is the modem up",
read `lte/state` first — it tells you signal and throughput without touching the
router. `mosquitto_sub -h 192.168.2.216 -t 'sally/telemetry/lte/#' -v`.

## Node inventory

- **Live:** QX210 router, `campingpi`, Roku, the cabin ESP32 (`sally-01`, config ready).
- **Planned:** Intel N100 mini-PC (always-on services host, Phase 3) and the ESP32
  fleet #0–7 (cabin-env, env satellites, fireside, tanks, power, fuel-keypad,
  backseat-ETA, city-water). Fleet contract + topics: `subsystems/telemetry/esp-fleet.md`.

## Canonical sources (read these for depth)

- `subsystems/network/README.md` — backbone, router, roadmap
- `subsystems/network/remote-access-vpn.md` — the WireGuard site node (authoritative)
- `subsystems/network/lte-monitoring.md` — LTE poller + MQTT + HA discovery
- `subsystems/network/router-serial-uart.md` — Pi↔router UART/RS232 (DTU, not console)
- `docs/network-diagram.md` — logical topology · `.env.example` — host/cred template

## Related skills

- [`sallynet-pi-ops`](../sallynet-pi-ops/SKILL.md) — deploying to / maintaining the Pi
- [`sallynet-interfaces`](../sallynet-interfaces/SKILL.md) — the `:8090` API + user UIs
