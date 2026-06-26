# Power — 12V House Battery, Charging, Monitoring

Sally's house battery + AC-DC converter + main charging wiring have all been recently upgraded. The system works, but voltage drops are making consistent charging difficult. This subsystem is about **diagnose first, instrument second**.

## Status

- Working: AC shore power → converter → battery → cabin loads
- Symptom: voltage drops cause inconsistent charging
- Unknown: where in the chain the drop is happening

## Field evidence (observed)

- **2026-06-25 — `campingpi` (the Pi 3B+) has logged under-voltage + throttling.** `vcgencmd get_throttled` returns `0x50000` → bit 16 *under-voltage has occurred* and bit 18 *throttling has occurred* since boot (neither active at read time). The Pi runs off the house 12V bus through a 12V→5V converter, so this is independent, always-on confirmation that the 5V rail — and by extension the 12V bus feeding it — sags under load. Re-check `get_throttled` after the wiring fixes below; target is `0x0`. Regardless of root cause, give the Pi a higher-headroom 12V→5V buck (or buck-boost) converter on a heavier feed — the RV "12V" bus swings 11.5–14.4 V and a marginal converter will keep browning it out.
- **2026-06-26 — it browns out *during boot*.** A deliberate reboot showed `get_throttled=0x50000` already set at **1 minute uptime** (under-voltage + throttling both flagged on a fresh boot, before any real load). So the sag isn't just under heavy use — the boot-time current surge alone trips it every power-on. This is the chronic-power smoking gun and the reason a converter/feed upgrade is the priority (also a real SD-corruption risk over time). A later sustained N64 session additionally tripped the soft thermal limit (`0xd0000`) — secondary; a $5 heatsink covers that.

## Inventory (as installed)

| Item | Spec |
|---|---|
| Engine batteries | 2× 12V @ 800 CCA each |
| Engine ↔ house tie | 12V disconnect + manual "badass switch" linking engine bank to house |
| House battery | ~600 CA car battery (single, rear) |
| Converter / charger | **Progressive Dynamics PD4135KW2B** — 35A 12V converter with Charge Wizard pendant |
| Charge feed to house | 20A inline fuse on the converter→house positive run |
| Engine starter assist run | 1 AWG to engine battery cutoff (manual switch tie) |

**AC breaker map:** (1) battery charger · (2/3) shore · (4) inverter *disconnected* · (5) kitchen plug · (6) exterior plug
**DC loads:** rear panel · main panel · lights ×2 · furnace

## Notes specific to this install

- The **PD4135** in its default mode floats at ~13.6 V — fine for flooded lead-acid. If the house battery is or becomes AGM/lithium, the **Charge Wizard pendant** should be set to the appropriate profile (or replaced with a smart-charge module). Check this as part of the diagnostic walk.
- 35 A converter into a ~600 CA (≈~100 Ah usable?) flooded battery is fine sizing — converter is not the bottleneck.
- The 20 A inline fuse on the house-side run is a hard cap. If voltage drop is severe under heavy charging, a partially-blown fuse element (high resistance) is a cheap first thing to check.
- The 1 AWG starter-tie run does **not** carry charging current normally — only when the switch is engaged for jump assistance. So drops on the *house* charge path won't show up on the engine side.

## Diagnose first (do not buy sensors until this is done)

Check in this order — each step rules out a class of fault. Stop when you find it.

1. **Voltmeter at converter output AND at battery posts under a known load.**
   A delta of more than ~0.3–0.5 V is a **wiring** problem, not a converter problem.
2. **Battery-to-chassis ground strap.** Classic 80s failure. Clean to bare metal, anti-oxidant compound, re-torque.
3. **All lugs end-to-end.** Under load, walk the path and feel for warm lugs — that's where current is being burned as heat.
4. **Cable gauge sanity check.** A 55 A converter over a 20 ft round-trip needs ~4 AWG. Factory 8 AWG is often the culprit on an "upgraded" install where the converter was swapped but the cabling wasn't.
5. **Charge profile vs battery chemistry.** Older converters stuck at 13.6 V float won't bulk-charge AGM or lithium properly. Confirm converter spec matches battery chemistry.
6. **Converter sized at ≥20% of bank Ah.** Undersized converter never finishes a charge cycle on a deeply-discharged bank.

## Instrument (after diagnosis)

Once the wiring is honest, add real instrumentation:

| Option | Cost | Notes |
|---|---|---|
| **Victron SmartShunt 500A** | ~$120–150 | One cut in the negative cable, fused positive sense wire, Bluetooth app. Integrates to Home Assistant via Victron MQTT or community ESPHome bridges. The standard hobbyist answer. |
| DIY: **INA226 + external 100A/75mV shunt + ESP32** | ~$30 total | ESPHome `ina226` component. **Must** use an external shunt — the INA226 breakout's onboard shunt is ~0.8A max. Self-hosted, integrates straight into the existing HA estate. |

> Deeper design exploration (two-tier shunt+hall architecture, INA228 vs INA226 for coulomb counting, the low-side ground trap, distributed branch monitoring) lives in [`dc-monitoring-brainstorm.md`](dc-monitoring-brainstorm.md).

## Safety

- Fuse the positive sense wire **at the battery post** (Victron ships a 1A fuse — use it).
- Battery compartment must vent outside.
- **No ESP32 inside the propane locker.** Don't put any spark-capable electronics in an enclosure that could pocket gas.

## Roadmap

1. Run the diagnostic checklist above; document what was found at each step in this folder
2. Fix the root cause (probably re-lug or up-size a run)
3. Install a SmartShunt (or INA226 + shunt) on the negative side
4. Bridge to Home Assistant via MQTT — alarm on low SOC / high charge current / unexpected discharge

## Next action

Multimeter check: converter output voltage vs battery-post voltage under a 20–30 A load (run the furnace fan or some 12V draw). Log the numbers in `configs/power/baseline-measurements.md`. Everything else waits on that number.
