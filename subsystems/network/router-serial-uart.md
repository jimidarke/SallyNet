# Pi ↔ QX210 Serial (RS232/RS485 DTU) Link

Wiring the Pi's UART to the QX210 router's **RS232/RS485 DTU** port (the port is a *data transfer unit* — Modbus RTU↔TCP / TCP passthrough — **not** a console; see CLAUDE.md and the LAN notes). Goal: give the Pi a serial path to the router's DTU for data passthrough.

## ⚠️ Gate before wiring: confirm the signal level
The QX210 connector is labelled `3V3 / GND / TX-B / RX-A` (pins do double duty: TX/RX in RS-232 mode, B/A differential in RS-485 mode). **It's almost certainly 3.3V TTL**, but verify non-destructively first — power the router, leave the port idle, meter **TX/B → GND**:

| Idle reading | Meaning | Action |
|---|---|---|
| ≈ **+3.3V** | 3.3V TTL UART | ✅ wire straight to the Pi GPIO (below) |
| ≈ **−5 to −12V** | true RS-232 | ❌ would **fry GPIO15** — needs a MAX3232 level shifter |
| ≈ 0 / floating / ~2.5V | likely RS-485 mode | set the port to RS-232 mode in UCI, or use an RS-485 transceiver |

Pi GPIO is 3.3V and **not 5V-tolerant**, so this check is mandatory. (Don't connect the router's `3V3` pin — leave it unconnected.)

## Validated wiring (3.3V TTL, RS-232 mode)
Cross TX↔RX, share ground. Confirmed against this Pi's silicon (`raspi-gpio funcs`: GPIO14 ALT0 = **TXD0**, GPIO15 ALT0 = **RXD0**):

| Router pin | Pi pin | |
|---|---|---|
| **TX/B** (router out) | **GPIO15 / phys pin 10 (RXD0)** | router transmits → Pi receives |
| **RX/A** (router in) | **GPIO14 / phys pin 8 (TXD0)** | Pi transmits → router receives |
| **GND** | **phys pin 6** | common ground (mandatory) |
| **3V3** | — | leave unconnected |

## Pi-side config — DONE (2026-06-26)
Applied to `campingpi` (Pi 3B+) and rebooted:
- `enable_uart=1` + `dtoverlay=disable-bt` in `/boot/config.txt` → the good **PL011** is now `/dev/serial0 → ttyAMA0` on GPIO14/15 (mini-UART demoted to `serial1 → ttyS0`).
- `console=serial0,115200` stripped from `/boot/cmdline.txt` (kept `console=tty1`) → no login/kernel console hogging the port; it's free for data.
- Bluetooth + WiFi disabled (`disable-bt`/`disable-wifi`, services off) — BT-disable is what frees the PL011.
- Boot files backed up to `/boot/*.sally.bak`.

So the port is **hardware-ready**: open `/dev/serial0` at the DTU's configured baud once wired.

## Status
- ✅ Pi side ready (`/dev/serial0` = PL011, no contention).
- ⏳ **Not yet physically wired** to the router, pending the level meter-check above.
- Alternative if you'd rather skip GPIO: a **USB-to-RS232 adapter** into a Pi USB port appears as `/dev/ttyUSB0` (no config/reboot needed) — but none is currently plugged in.

## Next action
Meter the QX210 TX/B→GND at idle to confirm 3.3V TTL. If TTL, wire per the table above and test with `screen /dev/serial0 <baud>` (or `stty`/`cat`) against the router's DTU setting. If it reads negative, add a MAX3232 first.
