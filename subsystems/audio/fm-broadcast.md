# FM Broadcast — BETS-1 Compliance is Non-Negotiable

The FM transmitter on Sally is for **rebroadcasting Sally's own audio to Sally and the camping group's adjacent sites**: cabin radio, kids at the picnic table with cheap FM earbuds, the neighbouring trailer in the same group, and a handful of $5 FM handhelds you can hand out to friends/family camping nearby. It is **never** a voice channel between vehicles (that's amateur radio — see [`subsystems/comms/amateur-radio-path.md`](../comms/)).

**Out of scope for FM:** the boat. Boat audio is delivered via Snapcast over WiFi (see [`bt-pairing.md`](bt-pairing.md) — boat scenario), which gives perfect sync + lossless audio + full group control. FM stays rigidly inside BETS-1 with the shipped whip.

## The hard rule

Under **ISED BETS-1** (Low Power Announcement Transmitters in the 88–107.5 MHz FM broadcast band), Canadian license-exempt operation requires:

> "The maximum power output of the transmitter into its antenna, with no modulation, shall not produce a field strength level of more than **100 µV/m** as measured at a distance of **30 metres**."

That's **< 1 µW EIRP**. Real-world range: ~50–150 ft on a good day, often less indoors.

ISED RIC-40 is explicit and quoted often enough to memorise:

> "Industry Canada has not exempted any 5 W FM broadcasting transmitters from authorization requirements, regardless of the equipment manufacturer, purpose of the transmission, or the affiliation of the operator."

Translation: **any** boosted transmitter is unlicensed broadcasting under the Radiocommunication Act, subject to seizure of equipment + fines. Don't.

## What this means in practice

| Allowed | Not allowed |
|---|---|
| BETS-1 certified USB / standalone FM transmitter at its rated power | Any power amplifier on the RF chain |
| The whip antenna that shipped with the transmitter | A high-gain stacked antenna that increases ERP past the cap |
| A modest external roof whip *if* it's at or below the gain the transmitter was certified with | A homemade dipole / J-pole / Yagi |
| Frequencies in the standard 88–107.5 MHz band, picked clear of local stations | Pirate frequencies outside the allocated FM band |

If the transmitter has a power switch, **use the lowest setting that gets to the cab radio + a boat 50 ft away**. That's the design goal — not "the next campsite over."

## Hardware (pick one)

| Option | Pros | Cons |
|---|---|---|
| **USB-line-in FM transmitter** (C.Crane FM Transmitter 2 or similar, ~$70) | Plug-and-play. Linux sees it as a USB audio sink. No firmware to write. | Less control; some models exceed BETS-1 — verify before buying |
| **Adafruit Si4713 breakout (~$40) + I2C-over-USB bridge (~$15)** | Tunable 76–108 MHz, RDS metadata (song title on the radio display), tiny | Need to write a small daemon. Mount on a Pi Zero 2 W for a one-board solution |
| **DIY Pi-based pifm-rds** | Cheapest, very flexible | Pi GPIO-modulated FM is notorious for spurious emissions and often exceeds compliance — **not recommended** for a permanent install |

Recommended for Phase 1: **C.Crane class USB-line-in transmitter** if a model with documented Canadian compliance is available; otherwise Si4713 on a Pi Zero 2 W.

## Antenna

- A short telescopic whip ships with most FM transmitters — that's the certified configuration
- Mounting it externally on Sally's roof improves real-world reception slightly without (necessarily) exceeding EIRP, because the cap is on field strength at distance, not on antenna placement
- **If you go from the shipped whip to a longer/external antenna, the burden of compliance moves to you.** Verify with a field-strength meter or a fellow ham with one, or just keep range-walking tests honest: if a portable FM radio in clear line of sight more than ~150 ft away still picks up Sally crisply, you're probably over-cap

## Why this is *still* useful at < 1 µW

- **The cab radio is < 3 m away** — totally solved
- **Driver gets the audio system in the cab** without putting on headphones (safety) — solved
- **Kids with $5 FM earbuds** instead of demanding their own BT cans — solved
- **Adjacent campsites in the same camping group** (~100–300 ft, often line-of-sight at a campground) — solved at this power level, honestly, without needing to push the cap
- **Cheap FM handheld giveaways** (e.g. a basket of $10 portable FMs at the trip start) — every group member gets the soundtrack on a device they don't have to charge or pair. Lowest-common-denominator output that the whole crew can use.
- **A Bluetooth speaker dies, a phone dies, a battery dies** — anyone with any FM radio can still tune in. Resilient.

## Frequencies

Pick a frequency in 88.1–107.9 MHz that's clear of broadcasters wherever Sally happens to be. Default to **88.1 MHz** (low end is usually less crowded in BC). When travelling, scan with the cab radio for dead-air and pick.

If using a Si4713, save the last-used frequency in NVS and let it persist across reboots so the family doesn't have to retune the cab radio every trip.

## Verification (Phase 4)

1. Tune the cab radio to the transmitter frequency from the driver's seat. Clear, music plays.
2. Walk 50 ft away from Sally with a portable FM radio. Still clear.
3. Walk to an adjacent campsite (~100–200 ft, line of sight). Should be receivable; reception degrades with obstacles. That's the intended coverage.
4. Walk a full campground row away (~400+ ft). Should be fading hard or gone. **If it's still crisp at that distance, the rig is over-cap — back it down.**
5. Confirm no local FM station you accidentally selected (you'd hear two stations talking over each other).

## See also

- [`source-switcher.md`](source-switcher.md) — how the FM transmitter joins the snapcast graph
- [`subsystems/comms/amateur-radio-path.md`](../comms/) — the legal duplex-voice path for between-vehicle conversation
