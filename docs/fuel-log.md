# Fuel Log

The plain-text source of truth for every fill-up. Update at the pump, not later. Even with no sensors on Sally yet, this alone will tell you her real-world fuel economy after ~5 entries.

**Calculation:** km between fills ÷ litres added × 100 = L/100 km. For mpg: 235.215 ÷ (L/100 km) = mpg (US).

**Operating reminder:** Drive on the **rear tank** with the selector in the **FRONT** position (see `docs/mechanics.md` for the dual-tank fault). All fuel goes into the rear fill unless otherwise noted.

## Log

| # | Date | Odometer (km) | Litres | Cost ($) | $/L | km since last | L/100 km | mpg (US) | Station / location | Notes (weather, terrain, A/C n.a., etc.) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | YYYY-MM-DD | | | | | | | | | First entry — set the baseline odometer |
|   | | | | | | | | | | |

> Drop the first row as soon as you fill up next. Don't worry about back-filling — start from the next pump.

## How to use this when telemetry comes online

Each row joins to the telemetry store (see `subsystems/telemetry/`) by **date + odometer**. The collector on the Pi knows the GPS track, elevation gain, average outside temp, average engine-bay temp, etc., for the interval between two odometer marks. A small dashboard panel will then compute:

- L/100 km **adjusted** for elevation gain (climb is expensive on the 460)
- L/100 km vs **outside temperature** (denser cold air = better fuel economy, all else equal)
- L/100 km vs **average speed** (the 460 cares; cruising 95 km/h vs 110 km/h is meaningful)
- Bay temperature percentile during the leg (catch overheating events alongside thirst)

Until then, just fill the table.

## Columns you don't need to write at the pump

- **L/100 km** and **mpg (US)** — derivable, fine to leave blank and compute later (or paste into a spreadsheet for the same)
- **$/L** — derivable from cost ÷ litres

## Columns worth writing at the pump

- Date, odometer, litres, cost, location — the irreducible minimum
- Notes — weather, headwind, mostly-highway vs mostly-mountain, recent maintenance, anything that would explain a weird mpg number two years from now when you're staring at the data wondering why
