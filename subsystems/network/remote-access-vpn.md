# Remote Access — Phone-Home WireGuard Site Node

How to reach Sally from anywhere. Sally's QX210 is on **cellular behind CGNAT** (carrier hands out **IPv6 + NAT64** — no inbound port-forward possible), so remote access uses a **dial-out** WireGuard "site node": a box on Sally dials home to a hub and bridges the whole LAN in. Reuses the existing `homeController` VPN backbone — see [`homeController/docs/network/remote-access.md`](../../../homeController/docs/network/remote-access.md) (Scenario B).

## Topology

```
  your laptop ──WG──► home hub (DarkeRouter) ◄──WG── campingpi (site node) ──► Sally LAN
   10.10.10.2          MikroTik, hub.example.net:51820       10.10.10.12, keepalive 25   NETMAP 192.168.2.0/24
```

- **Hub:** `wireguard1` on DarkeRouter (`192.168.1.1`), UDP **51820**, DDNS `hub.example.net`, pubkey `<hub-public-key>`.
- **Site node:** `campingpi` (Pi 3B+, `192.168.2.216`, wired) runs `wg-quick@wg-home`, dials the hub, NETMAPs Sally's `192.168.2.0/24`.

## Allocation (site index 12)

| | |
|---|---|
| Node overlay IP | `10.10.10.12` |
| Virtual LAN (seen from home) | `10.66.12.0/24` ⇄ real `192.168.2.0/24` (last octet preserved) |
| Node public key | `<node-public-key>` |
| Node config | `campingpi:/etc/wireguard/wg-home.conf` (private key stays on the Pi, never committed) |

Once live, from a machine on the home WG:
- `ping 10.66.12.1` → QX210 router · `http://10.66.12.1` → LuCI
- `ssh pi@10.66.12.216` → campingpi · Roku ECP at `10.66.12.227:8060`
- `ssh -D 1080 10.10.10.12 -N` → SOCKS straight through the node

## Status (2026-06-25)

- ✅ **Sally side DONE** — `wireguard-tools` installed, keypair generated, `wg-quick@wg-home` **active + enabled** (boot-persistent), tunnel dialing the hub (keepalive 25s). Verified: interface up at `10.10.10.12/32`, NETMAP rule present, handshake-initiations going out.
- ✅ **Hub side DONE (2026-06-25)** — peer + route + 2 firewall rules applied to DarkeRouter (index 12 confirmed free; existing peers were `.2`–`.5`). Applied **directly** as `claude@192.168.1.1` — from the home LAN the router's source-restricted mgmt accepts us, so the `nserver` bastion isn't needed. ⚠️ Gotcha: the `.rsc`'s multi-line `\` continuations + `#` comments **fail over non-interactive SSH** (`syntax error`); apply each command **flattened to one line** instead (or via `/import` after upload).
- ✅ **Verified end-to-end** — `site-sally` handshakes (`current-endpoint=198.51.100.20`, rx/tx flowing), and `/ping 10.66.12.1` from the hub reaches Sally's QX210 (~110–880 ms over cellular). First handshake took ~90 s after registration. If Sally powers off, it **auto-reconnects** when back online (persistent unit + keepalive 25).

### Using it (from a client on the home WG)
- `ping 10.66.12.1` → QX210 · `ssh pi@10.66.12.216` → campingpi · `http://10.66.12.1` → LuCI · Roku ECP `10.66.12.227:8060`
- `ssh -D 1080 10.10.10.12 -N` → SOCKS through the node
- **Permitted clients:** `jimi` (`10.10.10.2`) and `wsl-JimiDell` (`10.10.10.5`) — per-client `forward` rules on the hub (see `add-wg-site-peer-sally.rsc`). To add another client, mirror the rule for its overlay IP.
- **From this WSL dev box** (the `.5` client): `sudo wg-quick up ~/code/homeController/secrets/wg-clients/sally.conf` (split tunnel — overlay + Sally only, no home-LAN hairpin; passwordless via a `wg-quick` sudoers drop-in), then `ssh -i ~/.ssh/sally_campingpi pi@10.66.12.216`. `sudo wg-quick down …/sally.conf` when done. Note the conf must be short-named (interface name ≤15 chars).

## Implementation notes

- **No `iptables-persistent`.** Raspbian Buster is EOL — its main repo is dead (`netfilter-persistent`/`iptables-persistent` 404). So the NETMAP/MASQUERADE/FORWARD rules live as **`PostUp`/`PostDown`** in `wg-home.conf` instead; they re-apply on every `wg-quick up`, i.e. every boot via the enabled unit. (`wireguard-tools` itself installed fine from the still-live `archive.raspberrypi.org` repo.)
- **Host caveat:** this runs on the RetroPie box. Per the estate plan campingpi is meant to drift back to *pure RetroPie* once the Intel N100 mini-PC takes always-on services — at which point migrate this site node to the mini-PC (or go QX210-router-native via OpenWrt WG). The tunnel only works while campingpi is powered.
- **Power dependency:** campingpi has logged under-voltage (`get_throttled=0x50000`, see [`../power/`](../power/README.md)) — fix the 12V→5V feed so the always-on tunnel stays up reliably.

Cross-refs: [`../media/retropie-notes.md`](../media/retropie-notes.md) (the host), `homeController` VPN backbone.

## Next action

Operational. Two housekeeping follow-ups: (1) pull a fresh DarkeRouter `/export` into the `homeController` repo to capture the change; (2) once the Pi's power feed is fixed (`../power/`), confirm the tunnel stays up reliably across Sally power-cycles.
