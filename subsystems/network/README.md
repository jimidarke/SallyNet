# Network

QX210-NW2 Industrial 4G LTE WiFi router is the backbone. WiFi for cabin clients, cell for WAN by default, RS232 for SCADA-style data passthrough (not console).

## Status

- **Working:** Cell uplink; WiFi LAN to Roku + phones; **Pi on wired eth0**. Remote access into the whole LAN via a WireGuard site node on the Pi — see [`remote-access-vpn.md`](remote-access-vpn.md).
- **Pi↔router serial:** no USB-RS232 adapter is actually present — the link will use the Pi's **GPIO UART** (`/dev/serial0`, now enabled). Not yet wired; see [`router-serial-uart.md`](router-serial-uart.md).
- **Pain points:**
  - Want to auto-switch from cell uplink → WiFi-repeater when home WiFi is in range. Doable on the QX210 but clunky and dated through the web UI.
  - Hotel / campground captive portals are painful; no built-in portal helper.

## Important: RS232 ≠ console

The QX210 RS232 port is a **data DTU** (raw TCP/UDP passthrough + Modbus RTU↔TCP gateway). It is not a router console. The original "serial = router console override" plan does not work — to script the router from the Pi, use **SSH + UCI** over the LAN. A serial link (Pi GPIO UART, see [`router-serial-uart.md`](router-serial-uart.md)) is only useful for the DTU *data* path, never control.

References:
- [QX210 spec PDF](https://flytec.com.py/download/files/8123%20-%20QX210-Industrial-4G-Cellular-Router-Specification_compressed.pdf)
- [Installation Quick Guide](https://www.keennew.com/wp-content/uploads/2021/05/QX210-Installation-and-Configuration-Quick-Guide.pdf)
- [Manual on manuals.plus](https://manuals.plus/keennew/qx210-nw2-industrial-4g-lte-wifi-router-manual)

## Roadmap

1. **WiFi-as-WAN auto-switch at home** — Pi script that detects home SSID and SSHes into QX210 to flip the WAN profile. UCI keys to investigate: `network.wwan`, `wireless.wifi-iface[*]`.
2. **Captive portal helper** — small Pi script that watches for blocked traffic, MAC-clones a phone that successfully logged in (since the router doesn't ship a portal helper).
3. **Document existing UCI config** — pull current `/etc/config/network` + `/etc/config/wireless` from the router into `configs/network/` as a baseline.
4. **WiFi coverage extension for boat / campfire / adjacent sites** — Sally's audio system uses Snapcast over WiFi for the boat scenario (see `subsystems/audio/bt-pairing.md`). The QX210's stock WiFi typically reaches ~50–80 ft. **Confirmed: the QX210 has external antennas for both WiFi and cellular** — they're field-swappable, which makes the antenna upgrade the cheap path.

   **Step 1 (the cheap path — do this first):** Replace the QX210's stock WiFi antennas with higher-gain dual-band omnis.

   | Spec | Recommendation |
   |---|---|
   | Gain | **6 dBi** (best general-purpose) or 9 dBi for mostly-level-ground use |
   | Pattern | Omnidirectional — no aiming required |
   | Band | Dual-band 2.4 + 5 GHz (verify against QX210-NW2 spec; if 2.4-only, single-band is fine and cheaper) |
   | Quantity | **2** — the QX210 has 2×2 MIMO; replace both equally, don't mix gains (degrades MIMO) |
   | Connector | **Verify SMA-male vs RP-SMA-male first** — match the existing antennas. A photo of the centre pin tells you: pin = SMA, hole = RP-SMA. |
   | Cost | $15–30 each, $30–60 total |

   A 6 dBi omni ~doubles practical range vs the stock 2 dBi, bringing typical coverage from ~50–80 ft to ~100–150 ft. This alone usually solves boat + adjacent-site scenarios. **Field-test before assuming**: phone with Snapcast app, walk to the boat/site, watch for buffering.

   **Step 2 (if Step 1 isn't enough):** add a **USB-powered portable WiFi repeater** ($25–40) on a USB battery bank, placed midway. **Must support bridge / transparent repeater mode** — default "create-a-new-network" mode breaks Snapcast discovery (Layer-2 broadcast doesn't cross the NAT).

   **Step 3 (heavy-duty, marina use):** **12V outdoor AP** (Ubiquiti UniFi U6-Mesh class, $150–250) mounted high on Sally with a directional antenna — only if you regularly need dock 100+ ft away.

   **Avoid:** cheap consumer extenders that only run in "extender" (NAT'd) mode; second QX210 (no benefit over a cheaper extender).

5. **Cell antenna upgrade on the QX210** — lower priority. Sally's ANNTLENT cell booster already amplifies the carrier RF before it reaches the QX210's modem, so upgrading the QX210's own cell antennas adds little. Defer unless cell-side problems persist that the booster isn't fixing.

## Next action

Two things, in either order:
1. SSH into the QX210 from the Pi, capture the current UCI config (`uci export`) into `configs/network/uci-baseline.txt`, and confirm the LEDE/OpenWrt version + which UCI options are actually present on this firmware.
2. **Identify the QX210's WiFi antenna connector type** (SMA-male vs RP-SMA-male — photograph one stock antenna, check pin vs hole on the male end) **and confirm WiFi band(s)** (2.4-only vs dual-band 2.4+5 GHz). Once both are known, order 2× dual-band (or 2.4-only) 6 dBi omnis with the matching connector ($30–60 total) and swap. This single change is expected to bring boat / campfire / adjacent-site coverage into Snapcast range without any further hardware.
