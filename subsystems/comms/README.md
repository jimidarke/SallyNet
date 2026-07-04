# Comms — FRS Radios + Cell Booster

Cheap handhelds for the kids to keep in touch while exploring/biking. No phones, no cell coverage anyway. Plus the existing cell booster for when there *is* signal.

## Status

- **Working:** Roof-mount directional cell antenna + indoor cell signal booster. Good extension when there's a weak carrier signal.
- **In-flight:** Family FRS handhelds — lossy, get broken or lost, need a system.

## Two distinct comms problems

| Problem | Path |
|---|---|
| Kid handhelds while exploring on bikes / at the campsite | **FRS handhelds** (license-exempt 2W, fixed antenna — see below) |
| Adult driver-to-driver voice between Sally and another camper | **Amateur radio Basic Qualification + 2 m/70 cm mobile** — see [`amateur-radio-path.md`](amateur-radio-path.md). NOT the FM transmitter in `subsystems/audio/` (that's BETS-1 limited to campsite range and legally a one-way broadcast device only). |

## FRS / GMRS — the regulatory reality (Canada path)

Under ISED **SP 462/467 MHz**, license-exempt radios in Canada are capped at **2 W** with a **fixed/integral antenna**. Repeaters and removable antennas require a land-mobile radio licence. So:

- The "hack a handheld into a base with a roof whip" idea is **not legal license-exempt** in Canada
- Hands-down cheapest path: **good FRS handhelds, no antenna mods**
- Height beats power at these wattages — mount a charging cradle for one good FRS handheld high in Sally near a window, not down in a cabinet
- US-only future option (NOT applicable while travelling BC): family GMRS licence ($35/10yr) + Midland MXT115 mobile (~$150, 15W, repeater channels, magnetic-mount external antenna). Document as the upgrade path if travel patterns change; don't build it today.

References:
- [ISED SP 462/467](https://www.ic.gc.ca/eic/site/smt-gst.nsf/eng/sf08144.html)
- [twowayradiogear.ca — Do I need a radio licence in Canada?](https://twowayradiogear.ca/blogs/news-1/do-i-need-radio-license-canada-ised-guide)

## The plan

1. Pick a family channel + CTCSS / DCS tone — pre-program every handheld identically
2. Label every handheld (kid name + channel preset reminder)
3. Keep a spares drawer — assume loss is normal
4. One "Sally base" handheld in a powered cradle, high and near a window, on the same family channel
5. Charge stations near the door so radios actually get used and put back

## Existing handheld inventory

- **Uniden** FRS handhelds, multiple — kid loaners
- Charging stations live on Sally's **rear panel** alongside USB ports + voltage indicator
- Channel plan + tone not yet standardised — see roadmap

## Cell booster — what's installed

| | |
|---|---|
| Indoor unit | **ANNTLENT Cell Phone Signal Booster** — 850 / 1900 / 700 MHz, **Bands 2 / 5 / 12 / 17** |
| Coverage | LTE 4G / 3G / GSM — sized for Canadian carriers (Bell / Telus / Rogers) |
| Outdoor antenna | Directional, on extending roof spire mount |
| Indoor antenna | Standard panel/whip from the ANNTLENT kit |
| Use case | Home / cottage class booster repurposed for mobile cottage (Sally) — works well when there's *some* weak signal to amplify; will not conjure signal from nothing |

**Mounting orientation rule:** outside antenna at the front of the coach, indoor antenna toward the rear, with as much physical separation as the cabin allows so the inside antenna doesn't pick up the boosted output and oscillate (the booster will shut itself down when this happens — that's the "blinking red light of nope").

TODO:
- Confirm the booster's power source (12V house, AC inverter, or shore-only) and document
- Auto-shutdown on oscillation is confirmed (see mounting note above) — still need the reset procedure

## Roadmap

1. Pick + buy 4–6 FRS handhelds + chargers; choose family channel/tone
2. Install in-cabin powered cradle for the "Sally base" handheld
3. Print labels for handhelds + dock + a small "how to use" card for kids
4. Document existing cell booster components into this folder
5. **Amateur radio path** — study + write Basic Qualification (ideally with Honours, same effort, much bigger reward). See [`amateur-radio-path.md`](amateur-radio-path.md). Parallel track, doesn't block FRS work.

## Next action

Inventory the handhelds you already have (model, condition, batteries) before buying more — there may be a salvageable set already in the truck.
