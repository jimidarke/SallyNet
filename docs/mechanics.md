# Mechanics — Sally

The page you'd want at a strange gas station — not a shop manual. Keep it short, keep it true. Update when something is serviced or a quirk is discovered.

## Identity

| | |
|---|---|
| **VIN** | `…B40728` |
| **Year / Make / Model** | 1985 Ford E-350 Econoline cutaway |
| **Engine** | 7.5L (460 cu in) V8 EFI |
| **Assembly plant** | Lorain, OH |
| **GVWR** | 4989 kg (~11,000 lb) |
| **GAWR front / rear** | 1905 kg / 3356 kg |
| **Drivetrain** | RWD (Ford E-series motorhome chassis) |

### VIN decode

| Pos | Char | Meaning |
|---|---|---|
| 1 | · | USA |
| 2 | · | Ford |
| 3 | · | Truck / MPV |
| 4–5 | · | Heavy-duty brake / Econoline |
| 6 | · | Series 350 |
| 7 | · | Cutaway / cab-chassis (motorhome conversion body code) |
| 8 | · | **7.5L (460 cu in) V8 EFI** |
| 9 | · | Check digit |
| 10 | · | 1985 model year |
| 11 | · | Lorain, OH assembly plant |
| 12–17 | B40728 | Sequence |

## Chassis quirks

- **Power steering** — proper, not the older armstrong setup
- **Foot-press high-beam switch** on the driver-side floor pan

## Previous-owner engine mods

- **Beefed-up engine fan** — looks like a heavier-duty replacement vs the stock unit. Probably aimed at heat management on the 460 V8, which historically runs warm in a motorhome chassis.
- **Cutout in the engine air-intake area** for additional inflow — modifies the stock airbox/intake geometry. Document the exact location with a photo next time the doghouse is off. Note: this can change MAF/fuel-trim behaviour on the EFI 460; if any drivability quirks appear, this mod is on the suspect list.

## Known issues (in flight)

- **Minor oil leak → light smoke.** Source not yet confirmed. Owner has a suspicion of the location; **mechanic to diagnose**. Until then: watch the dipstick at each fuel stop, top up as needed, document each top-up in the service log below.

## Fuel system — known fault (live)

Sally has dual fuel tanks (front + rear) and a tank-selector switch. The system is **mis-plumbed/mis-wired**:

| Switch position | Gauge shows | Engine pulls from | Result |
|---|---|---|---|
| FRONT | Front tank level | **Rear tank** | Runs fine. Gauge is wrong (shows the tank you're *not* using). |
| REAR | Rear tank level | Tries front, fails | Stalls in a couple of minutes. Useful only to spot-check rear tank level by toggling, then switching back to FRONT. |

**History:** A previous shop replaced the fuel pump. The pump replacement didn't fix the underlying fault — it's almost certainly in the **tank-selector valve** or its actuator wiring (the 6-port valve that switches both feed/return and the sending-unit signal). Either the valve is internally crossed/stuck, or the wiring to the valve and the gauge harness are crossed independently.

**Operating procedure today:**
- Drive on the **rear tank only**, switch in **FRONT** position
- **Trust trip distance, not the gauge.** 460 V8 in this body realistically gets 6–8 mpg
- Toggle to REAR briefly only to spot-check actual fuel level, then back to FRONT before stalling

**Future diagnosis (not a job for the campground):**
1. Locate the tank selector valve on the frame rail (6-port + sending-unit selector)
2. Verify with a meter: switch position vs which sending-unit line is connected to the gauge
3. Confirm whether the valve actuator + check-valve is the issue, vs harness labels being swapped
4. Repair will likely be valve replacement; budget a real shop visit, not a roadside fix

## Fluids & capacities

| Fluid | Spec | Capacity | Last service |
|---|---|---|---|
| Engine oil | **10W-30** (in use) | ~6 qt w/ filter | 2026-05-17 top-up ~3.5 L |
| Coolant | Green ethylene glycol mix | ~20 qt | TBD |
| Power steering | Mercon / Type F (confirm — '85 460 typically Mercon) | — | — |
| Brake fluid | DOT 3 | — | TBD |
| Automatic transmission | Mercon (C6 auto on most E-350 460s of this era — confirm) | — | **Dipstick OK 2026-05-17** |
| Differential | 80W-90 GL-5 | — | TBD |

> Fill these in next time the engine bay is open. Photograph caps + reservoirs; add photos to this folder.

## Quirks log

| Quirk | First noted | Notes |
|---|---|---|
| Dual-tank selector swapped (see Fuel System) | (pre-existing, ongoing) | Pump was replaced, root cause is upstream at the selector valve / wiring |
| Gauge reads inactive tank | (with above) | Effectively decorative — drive by trip distance |
| No A/C | factory | Plan trips for shade + elevation, not relief from A/C |
| Minor oil leak / light smoke | 2026-05-17 | Owner has a suspicion of location; mechanic to diagnose. Top-up + watch in the meantime. |
| Non-stock engine fan (previous owner) | (pre-purchase) | Heavier-duty replacement for the 460's heat load |
| Air-intake cutout (previous owner) | (pre-purchase) | Hole cut in intake area for more inflow — can shift EFI fuel trim |

## Service log

Append-only. Newest at top.

| Date | What | Notes |
|---|---|---|
| 2026-05-17 | Engine oil top-up — ~3.5 L of 10W-30 | Was near empty on dipstick. Minor oil leak / light smoke present — mechanic to diagnose. |
| 2026-05-17 | Transmission dipstick check | Fluid level OK, no top-up needed. |
| ~2024 | Sewage outlet connector replaced | Plumbing-side maintenance |
| ~2024–2025 | Water pump replaced | DPHCF42-12V installed |
| (date TBD, pre-purchase) | Fuel pump replacement | Did NOT resolve dual-tank fault — see Fuel System |
| (pre-purchase, previous owner) | Engine fan upgrade + air-intake cutout | See "Previous-owner engine mods" above |

## House systems (cross-reference)

- Holding tanks (fresh/grey/black) + propane: see [`subsystems/tanks/`](../subsystems/tanks/)
- House battery + 12V system: see [`subsystems/power/`](../subsystems/power/)
