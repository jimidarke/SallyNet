# Remote access — WireGuard phone-home site node

Deep reference for reaching Sally from anywhere. Authoritative doc:
`subsystems/network/remote-access-vpn.md` (this condenses it to the operational facts).

## Why dial-out

Sally's QX210 is on **cellular behind CGNAT** — the carrier hands out IPv6 + NAT64,
so there is **no inbound port-forward**. Remote access is therefore a **dial-out**
WireGuard "site node": `campingpi` dials home to a hub and NETMAPs the whole LAN in.
Reuses the existing `homeController` VPN backbone (Scenario B).

## Topology

> **Placeholders:** the hub hostname (`hub.example.net`), UDP port (`51820`), WireGuard public keys and
> WAN IPs (RFC 5737 `203.0.113.x` / `198.51.100.x`) in this doc are stand-ins. The real values live in the
> gitignored `PRIVATE.md` at the repo root (operator-only); on the Pi they are in `/etc/wireguard/wg-home.conf`.

```
  your laptop ──WG──► home hub (DarkeRouter) ◄──WG── campingpi (site node) ──► Sally LAN
   10.10.10.2          MikroTik, hub.example.net:51820       10.10.10.12, keepalive 25   NETMAP 192.168.2.0/24
```

- **Hub:** `wireguard1` on DarkeRouter (`192.168.1.1`), UDP **51820**, DDNS `hub.example.net`,
  pubkey `<hub-public-key>`.
- **Site node:** `campingpi` (`192.168.2.216`, wired) runs `wg-quick@wg-home`, dials the
  hub, NETMAPs Sally's `192.168.2.0/24`.

## Allocation (site index 12)

| | |
|---|---|
| Node overlay IP | `10.10.10.12` |
| Virtual LAN (from home) | `10.66.12.0/24` ⇄ real `192.168.2.0/24` (last octet preserved) |
| Node public key | `<node-public-key>` |
| Node config | `campingpi:/etc/wireguard/wg-home.conf` (private key stays on the Pi) |

## Using it (from a client on the home WG)

| Reach | Command |
|---|---|
| QX210 router | `ping 10.66.12.1` · LuCI `http://10.66.12.1` |
| Pi `campingpi` | `ssh pi@10.66.12.216` (or `-i ~/.ssh/sally_campingpi`) |
| sally-api | `curl -s http://10.66.12.216:8090/api/health` |
| Roku ECP | `http://10.66.12.227:8060/...` |
| SOCKS proxy | `ssh -D 1080 10.10.10.12 -N` |

**Permitted clients** (per-client `forward` rules on the hub): `jimi` (`10.10.10.2`)
and `wsl-JimiDell` (`10.10.10.5`). To add another, mirror the rule for its overlay IP.

**From the WSL dev box** (the `.5` client) — split tunnel (overlay + Sally only, no
home-LAN hairpin), passwordless via a `wg-quick` sudoers drop-in:

```bash
sudo wg-quick up   ~/code/homeController/secrets/wg-clients/sally.conf
ssh -i ~/.ssh/sally_campingpi pi@10.66.12.216
sudo wg-quick down ~/code/homeController/secrets/wg-clients/sally.conf
```

The conf interface name must be ≤15 chars (hence the short `sally` name).

## Self-healing watchdog

The stock `wg-quick@wg-home` unit can die and stay dead two ways keepalive can't fix:

1. **Boot race** — `campingpi` boots before the QX210 has LTE; `wg-quick` is
   `Type=oneshot`, so if the hub DNS can't resolve at boot it fails and never retries.
2. **DNS staleness** — `wg-quick` resolves the endpoint hostname only once; the hub's
   `hub.example.net` is *dynamic* DNS, so a hub WAN-IP change leaves the Pi firing keepalives
   at a dead address (caused an observed 11-minute-stale handshake).

Fix: `scripts/wg-watchdog.sh` + `configs/network/sally-wg-watchdog.{service,timer}`,
deployed to `/opt/sally/net/wg-watchdog.sh`, fired every 60 s (`OnBootSec=60`,
`OnUnitActiveSec=60`). Each tick: (re)start the unit if inactive (the boot-race retry),
re-resolve `hub.example.net` and update the peer endpoint if the hub IP moved, and bounce the
tunnel if no handshake within `STALE_AFTER` (150 s). Deploy with
`scripts/deploy-wg-watchdog.sh`. The hub host/port/key come from the `[Peer]` `Endpoint` +
`PublicKey` in `/etc/wireguard/wg-home.conf`; override via env: `STALE_AFTER`, `HUB_HOST`,
`HUB_PORT`, `HUB_PUBKEY`.

The watchdog only papers over brownout drops — **also fix the Pi's 5 V feed**
(`subsystems/power/`); under-voltage is logged on `campingpi`.

## Ops gotchas

- **Bufferbloat under streaming:** ~3–4 s RTT while a movie/tablet plays → multi-RTT
  `scp`/`rsync` stalls. Use a single-connection base64-inline transfer (one SSH, files
  inlined) — see `scripts/deploy-lte-monitor.sh` for the pattern. `deploy-wg-watchdog.sh`
  is multi-hop scp and may itself time out under load; run it when the link is quiet.
- **No `iptables-persistent`** (Buster EOL, repo 404). The NETMAP/MASQUERADE/FORWARD
  rules live as `PostUp`/`PostDown` in `wg-home.conf` and re-apply on every `wg-quick up`.
- **Host caveat:** the site node runs on the RetroPie box. When the N100 takes always-on
  services (Phase 3), migrate the site node to it (or go QX210-router-native via OpenWrt
  WG). The tunnel only works while `campingpi` is powered.
