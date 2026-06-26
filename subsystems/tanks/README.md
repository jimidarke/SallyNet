# Tanks — Holding (fresh/grey/black) + Propane

Two very different stories in one folder. Holding tanks are fair game for instrumentation. The propane tank is **not**.

---

## Propane — HANDS OFF

The under-floor propane tank, its OPD valve, the regulator, the flex hoses, and any pressurised line are **out of scope** for hobbyist modification. Do not drill, tap, splice, re-route, or service these. If something is wrong with the gas system, it goes to a certified RV propane technician, full stop.

**What IS fair game (zero modification to the gas system):**

| Addition | Purpose | Notes |
|---|---|---|
| 12V wired propane leak detector, mounted ~6" off the floor in the living area | Safety | Propane is heavier than air; mount low. Replace every ~7 years (the sensor element ages). |
| **Mopeka Pro Check** magnetic ultrasonic sensor stuck to the **underside** of the steel propane tank | Level reading | ~$40, BLE to phone, or via an ESPHome BLE proxy → Home Assistant. Reads through the steel tank wall by ultrasound — no penetration, no modification of anything pressurised. |

---

## Holding tanks — fresh / grey / black

### Current state

Each tank has 4–5 stacked vertical probe electrodes original to Sally (1980s design). They work as conductive switches: liquid bridges each probe to a common ground, in-line resistors return a distinct level signal, dash panel lights step E/⅓/⅔/F. Failure modes already showing:
- **Black tank:** TP / grease drapes across the upper probes and keeps the circuit closed → reads "full" forever
- **Pigtail lugs:** corroded after decades, intermittent contact

### Retrofit ladder (cheapest → best)

1. **Horst Miracle Probes** (~$40–60/set) — drop-in screw replacements with a Teflon shield over the brass tip; the shield is the actual fix for the fouling problem. Keeps the OEM dash panel. Lowest-effort meaningful upgrade.
2. **Garnet SeeLevel II** (~$170–350) — external capacitive PCB strips taped to the **outside** of each tank. 1% resolution, no penetration, no fouling possible. The most-recommended modern fix in RV forums. **Works on plastic/poly tanks only** — first action item is to verify Sally's tanks aren't steel before committing.
3. **DIY ESP32 + JSN-SR04T waterproof ultrasonic** (~$25, ESPHome `ultrasonic` component) — fine for fresh, OK for grey, **bad idea for black** (TP wads and splashes against the transducer face produce garbage readings).
4. **Hydrostatic pressure sensor at tank bottom** — accurate but requires drilling the bottom of a 40-year-old tank. Not worth the risk. Skip.

### Recommended path (current decision — 2026-06-26)

**Primary — reuse the existing 1980s stacked probes via an ESP32 + CD4051 analog mux** (~$20–30):
one ADC pin time-multiplexed across the probe taps, per-tank empty/full calibration in firmware.
Minimal intrusion, keeps the OEM dash panel. **Fallback — Garnet SeeLevel II** *only if* the
under-floor tank-material photo rules out probe reuse. The ladder above lists the other options
considered (not chosen). Propane stays non-invasive (Mopeka clip-on + 12V leak detector).

_Earlier write-up (kept for reference):_

If tanks are plastic/poly → **SeeLevel II**, full retrofit, retire the OEM panel.
If tanks are steel → **Horst Miracle Probes** as a much cheaper upgrade that keeps the OEM panel honest.

In parallel, an ESP32 + JSN-SR04T on the **fresh tank only** could feed a Home Assistant dashboard as a low-stakes experiment.

## Roadmap

1. Verify tank construction (plastic/poly vs steel) — photograph and tag each tank
2. Pick retrofit path based on construction
3. Buy + install
4. Optional: parallel ESPHome ultrasonic on fresh tank for HA integration
5. Add Mopeka Pro Check to the propane tank + 12V wired leak detector in the cabin

## Next action

Get under Sally with a flashlight, photograph each holding tank, and identify the material (plastic/poly vs steel) — this decision gates the entire retrofit choice.
