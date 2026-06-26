# DC Power Monitoring — Architecture Brainstorm

**Status:** Feasibility / idea-tossing. Nothing decided, nothing bought beyond what's already on hand. Captured 2026-06-24 for later followup.

**Hard prerequisite:** This sits *behind* the diagnostic checklist in [`README.md`](README.md) — "diagnose first, instrument second." Do not build monitoring on top of an un-diagnosed wiring fault; you'll just be measuring the fault with high precision. Everything below waits on the baseline multimeter numbers landing in `configs/power/baseline-measurements.md`.

## Goal

Understand the **charge/discharge cycle of the house battery** (true state-of-charge over time), and longer-term add voltage/current monitors at other points in the vehicle. Integrate natively into the existing MQTT / Home Assistant estate rather than a closed app.

## Parts already on hand

- High-current **shunts**
- Low-current **hall-effect** sensor modules
- A pile of **ESP32** devices

## Two design instincts (both judged correct)

1. **No shunt in the cranking path.** Confirmed good. To pass 600+ CCA a shunt would need to be 50–100 µΩ, which buries the normal-house-load signal in noise — a sensor optimized for the one event we don't care about. The cranking circuit is where a **hall clamp** belongs *if* ever instrumented (zero insertion loss, isolated, doesn't care it's 600 A). Later, not now.
2. **Monitor the secondary (house) side only.** Confirmed good. The primary↔secondary disconnect gives a clean measurement boundary: all house-side current flows through a bounded set of paths (PD4135 in, loads out, the 1 AWG starting-support link when combined).

## Core architecture: two tiers, two technologies, by job

Shunts and hall sensors are good at **opposite** things, and we own both — so assign by role rather than pick one.

| Tier | Job | Technology | Why |
|---|---|---|---|
| **Tier 1** | House-battery "source of truth" — coulomb-counted true SoC | **Shunt** (precision, on the negative) | SoC = ∫I·dt. Sensor offset gets integrated too: a constant 50 mA phantom offset = **~1.2 Ah of imaginary drift per day, forever**. Shunts have near-zero, low-drift offset; open-loop hall offset drifts with temperature — fatal for integration. |
| **Tier 2** | Per-branch monitoring — furnace blower, water pump, lighting, converter output, starting-support link | **Hall** (clamp around the wire) | Non-invasive (no cable cuts), isolated, and **sidesteps the ground-path trap** that haunts the Tier-1 shunt. Branch telemetry doesn't need 0.1% accuracy and isn't integrated for SoC, so hall's weaknesses don't bite. |

The EV-battery / metrology literature lands on the same split: **shunt for SoC, hall for the rest.**

## Recommended Tier-1 chip: INA228 (not INA226)

For the source-of-truth monitor, push for the **INA228** over the more commonly-blogged INA226:

- **Hardware charge accumulator** — counts coulombs *in silicon*. The INA226 makes the ESP32 do the integration in software.
- This matters specifically because **our ESP32s are on WiFi and WiFi nodes reboot.** If the MCU is doing the integration and it reboots mid-discharge, the coulombs are lost and SoC lies. The INA228 keeps counting through the reboot; the ESP just re-reads the accumulated register on wake.
- 20-bit ADC (vs 16-bit) and uses its own temperature reading to compensate the shunt's resistance drift.
- ESPHome supports it natively, including the `charge_coulombs` sensor (INA228/229 only).
- Barely more expensive than the INA226.

> Note: the existing README "Instrument" table lists INA226 — INA228 supersedes that recommendation for the SoC role specifically.

## The gotcha that will actually bite: the low-side ground trap

A negative-side battery shunt only tells the truth if **the only thing bolted to the house battery negative post is the shunt.** Every load ground, charger negative, and the chassis bond must land on the *other* (load) side of the shunt. Any negative wire on the battery-side post is an invisible bypass → uncounted current → SoC drifts.

This is **vehicle-specific and hard** because the chassis itself is a ground conductor:

- If the house battery negative touches chassis anywhere except through the shunt, current sneaks home through the steel, uncounted.
- The **starting-support 1 AWG link** makes it spicier: when the disconnect is combined, engine↔house current can return via chassis. As long as the house battery's *only* negative connection is the shunt, that current still passes through it correctly — but a second chassis bond on the battery-side post breaks everything.

**→ Make-or-break question before building anything: how many things are currently bolted to the house battery negative post?** If more than one, this is a re-grounding job first and a sensor project second.

This is also the strongest argument for leaning on Tier-2 hall: a clamp around a *positive* branch wire doesn't care about ground topology at all.

## Other threads to pull

- **The monitor is itself a load.** Always-on ESP32 + sensor ≈ 0.5–1 W continuous parasitic draw on the very battery being measured (correctly counted, but know it's there). Continuous coulomb counting means **no deep-sleep** on the Tier-1 node.
- **Powering the nodes off 12 V:** the bus swings ~11.5–14.4 V, all comfortably above a 5 V rail → a plain **buck** regulator is correct here; no buck-boost needed (we're never stepping up to reach 5 V).
- **Automotive transients are nasty.** Alternator load-dump, 460 EFI noise, converter switching ripple. Design in TVS + input filtering from the start or expect bricked ESP32s.
- **SoC math is more than ∫I·dt.** For flooded lead-acid it needs: (a) periodic **resync** — when the PD4135 hits float, call it 100% and zero the drift; (b) **Peukert correction** — lead-acid delivers less capacity at high discharge rate; (c) **temperature compensation** of capacity. This is the real reason people buy a Victron SmartShunt: that math is tuned. Our DIY value is native MQTT integration (Victron only bridges via VE.Direct).
- **Network shape for the ESP32 fleet.** A swarm of WiFi clients on the QX210 is the obvious path but not the only one. **ESP-NOW** (peer-to-peer, no AP association, survives router reboots) with one node as the ESP-NOW→MQTT gateway keeps the sensor swarm off the main WiFi association table — appealing given the Halloween radio-contention lesson.
- **Kirchhoff reconciliation (Phase-2 payoff).** With main shunt + branch hall sensors, Σ(branches) should equal main − battery. When it doesn't, you've found either a sensor needing re-zero or — more interesting — an **unaccounted drain** (parasitic leak, corroded ground bleeding to chassis). Turns monitoring into diagnostics, which on a 40-year-old rig with known voltage-drop symptoms is arguably the real prize.

## Open questions to resolve before committing

1. **DIY-everything vs. hybrid?** ESP32+shunt as the SoC source of truth (full control, native MQTT, but we own the Peukert/resync math) — or Victron SmartShunt as the *battery* monitor + ESP32/hall fleet for *branch* telemetry (SmartShunt has solved the hard SoC problem; the hall work is where our unique value is anyway)?
2. **What's actually bolted to the house battery negative post right now?** Make-or-break for the whole Tier-1 shunt approach.
3. **One battery monitor, or eventually SoC-grade accuracy on the engine pair too?** Decides whether we build one tier or a framework that scales.
4. **ESP-NOW mesh vs. plain WiFi+MQTT** for the sensor swarm — how much to insulate this from the QX210.

## Cross-references

- [`subsystems/power/README.md`](README.md) — inventory, diagnostic checklist (the prerequisite), safety, existing instrument options
- [`subsystems/telemetry/README.md`](../telemetry/README.md) — the cabin glance-mode UI already wants a "cabin battery voltage (shunt feed)"; this is that feed
- Safety reminders from the README still apply: fuse the positive sense wire **at the battery post**; battery compartment vents outside; **no spark-capable electronics in the propane locker.**

## Sources

- [Melexis — shunt vs hall for battery current sensing](https://www.melexis.com/en/news/tech-talks/a-view-to-a-battery-current-sensor-shunt-or-hall)
- [Isabellenhütte — shunt-based vs magnetic sensing](https://www.isabellenhuetteusa.com/wp-content/uploads/2020/12/Isabellenhutte_EV-Shunt-Resistors_tech-article_final.pdf)
- [ESPHome INA2xx component (INA226/228/229)](https://esphome.io/components/sensor/ina2xx/)
- [TI INA228 product page](https://www.ti.com/product/INA228)
- [TI TMCS1100 datasheet (zero-drift hall option for Tier 2)](https://www.ti.com/lit/ds/symlink/tmcs1100.pdf)
- [Victron SmartShunt install — grounding rules / low-side trap](https://www.victronenergy.com/media/pg/SmartShunt/en/installation.html)

## Next action

Answer open question #2 — inspect the house battery negative post and record exactly what lands on it (in `configs/power/baseline-measurements.md` alongside the diagnostic numbers). The whole Tier-1 shunt design is gated on that post being a single-connection point.
