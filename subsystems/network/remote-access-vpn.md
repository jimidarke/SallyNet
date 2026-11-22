# Remote Access — Phone-Home WireGuard Site Node

How to reach Sally from anywhere. Sally's QX210 is on **cellular behind CGNAT** (carrier hands out **IPv6 + NAT64** — no inbound port-forward possible), so remote access uses a **dial-out** WireGuard "site node": a box on Sally dials home to a hub and bridges the whole LAN in. Reuses the existing `homeController` VPN backbone — see [`homeController/docs/network/remote-access.md`](../../../homeController/docs/network/remote-access.md) (Scenario B).

## Topology

> **Placeholders:** the hub hostname (`hub.example.net`), UDP port (`51820`), WireGuard public keys and
> WAN IPs (RFC 5737 `203.0.113.x` / `198.51.100.x`) in this doc are stand-ins. The real values live in the
> gitignored `PRIVATE.md` at the repo root (operator-only); on the Pi they are in `/etc/wireguard/wg-home.conf`.

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

## Self-healing watchdog (2026-06-26)

The stock `wg-quick@wg-home` unit can die and **stay dead** two ways the keepalive can't fix:

1. **Boot race** — `campingpi` boots faster than the QX210 acquires LTE. `wg-quick` is `Type=oneshot`; if the hub DDNS can't resolve at boot it **fails and never retries** (and oneshot units *reject* `Restart=`, so a drop-in is not an option).
2. **DNS staleness** — `wg-quick` resolves the `Endpoint` hostname **only once**, at setconf time. The hub sits behind `hub.example.net` *dynamic* DNS, so a hub WAN-IP change leaves the Pi firing keepalives at a dead address forever. (This is what caused the observed **11-minute-stale** handshake while Sally's LAN was otherwise healthy.)

Fix: a watchdog timer on the Pi — **`scripts/wg-watchdog.sh`** + **`configs/network/sally-wg-watchdog.{service,timer}`**, deployed to `/opt/sally/net/wg-watchdog.sh`, fired every 60s by `sally-wg-watchdog.timer` (`OnBootSec=60`, `OnUnitActiveSec=60`). Each tick:
- (re)starts `wg-quick@wg-home` if the unit isn't active → **the watchdog *is* the boot-race retry** (covers #1);
- re-resolves `hub.example.net` and updates the peer endpoint in place if the hub IP moved (covers #2);
- restarts the tunnel if no handshake within `STALE_AFTER` (150s) — catches any remaining wedge.

Deploy with **`scripts/deploy-wg-watchdog.sh`** (key-based over the tunnel; `PI_HOST` defaults to `10.66.12.216`). Verified 2026-06-26: timer enabled + active, manual run logged `ok (handshake 70s ago, hub 203.0.113.10)`. The hub host/port/key are read from the `[Peer]` `Endpoint` + `PublicKey` in `/etc/wireguard/wg-home.conf` (nothing endpoint-specific is committed); override via env (`STALE_AFTER`, `HUB_HOST`, `HUB_PORT`, `HUB_PUBKEY`). Note this only papers over brownout-induced drops — fix the Pi's 5V feed too (see [`../power/`](../power/README.md)).

> Ops gotcha: deploying over cellular while Sally is streaming (movie/tablet) → **bufferbloat ~3–4 s RTT**; multi-round-trip `scp` stalls. Use the single-connection base64 path (one SSH, files inlined) instead — `deploy-wg-watchdog.sh` is multi-hop and may time out under load.

## Implementation notes

- **No `iptables-persistent`.** Raspbian Buster is EOL — its main repo is dead (`netfilter-persistent`/`iptables-persistent` 404). So the NETMAP/MASQUERADE/FORWARD rules live as **`PostUp`/`PostDown`** in `wg-home.conf` instead; they re-apply on every `wg-quick up`, i.e. every boot via the enabled unit. (`wireguard-tools` itself installed fine from the still-live `archive.raspberrypi.org` repo.)
- **Host caveat:** this runs on the RetroPie box. Per the estate plan campingpi is meant to drift back to *pure RetroPie* once the Intel N100 mini-PC takes always-on services — at which point migrate this site node to the mini-PC (or go QX210-router-native via OpenWrt WG). The tunnel only works while campingpi is powered.
- **Power dependency:** campingpi has logged under-voltage (`get_throttled=0x50000`, see [`../power/`](../power/README.md)) — fix the 12V→5V feed so the always-on tunnel stays up reliably.

Cross-refs: [`../media/retropie-notes.md`](../media/retropie-notes.md) (the host), `homeController` VPN backbone.

## Next action

Operational + self-healing (watchdog deployed 2026-06-26). Follow-ups: (1) pull a fresh DarkeRouter `/export` into the `homeController` repo to capture the peer change; (2) once the Pi's power feed is fixed (`../power/`), confirm the tunnel survives Sally power-cycles unattended — watch `journalctl -u sally-wg-watchdog.service` across a cold boot to verify it recovers the boot race in the wild (not just the same-Pi-only reboot tested so far).
