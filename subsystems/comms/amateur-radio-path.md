# Amateur Radio — Camper-to-Camper Voice, Done Legally

## Why this exists

The idea was: two campers, each with an FM transmitter on Sally's audio rig + a handheld mic, run voice in opposite directions on different frequencies. Hack a duplex CB out of the FM band, no licensing, no FRS.

It doesn't work — under ISED rules:

- Canadian license-exempt FM is capped at < 1 µW EIRP (BETS-1: 100 µV/m @ 30 m). That's **campsite range**, not camper-to-camper.
- ISED RIC-40 is explicit: "Industry Canada has not exempted any 5 W FM broadcasting transmitters from authorization requirements, regardless of the equipment manufacturer, purpose of the transmission, or the affiliation of the operator."
- The FM broadcast band 88–108 MHz is allocated for **broadcasting** (one-way). Two-way voice is outside its allocation — no license would authorise that use even if you applied for one.
- Boosting an FM transmitter past the BETS-1 cap is unlicensed broadcasting under the Radiocommunication Act. Real fines, real seizures, real enforcement.

But the underlying need — proper long-range, license-friendly voice between two vehicles in the BC backcountry — is exactly what amateur radio exists for. The user already volunteered: "I don't mind taking a course or whatever helps the CRTC." Good news: the course already exists, it's well-trodden, and it's free.

## The Basic Qualification (the "course")

| | |
|---|---|
| **Exam** | 100 multiple-choice questions |
| **Pass** | 70% |
| **Fee** | $0 (volunteer accredited examiners administer it free) |
| **License fee** | $0 in Canada. Permanent. The callsign is yours for life. |
| **Question bank** | Public ([ISED Amateur Radio Exam Generator](https://ised-isde.canada.ca/site/amateur-radio-operator-certificate-services/en/amateur-radio-exam-generator)) — the real exam draws from this published pool, so you can practice the exact questions |
| **Study time** | A weekend or two of focused study for someone technically comfortable; longer if you want to actually understand the physics rather than memorise |
| **Study materials** | RAC study guide; [HamStudy.org](https://hamstudy.org/) (free flashcards driven by spaced repetition); Coax Publications "The Canadian Amateur Radio Basic Qualification Study Guide" |
| **Where to write** | [Find an accredited examiner](https://ised-isde.canada.ca/site/amateur-radio-operator-certificate-services/en/accredited-examiners) — usually a local club volunteer; they'll administer the exam at a coffee shop or club night |

## What Basic grants you

> Basic Qualification grants operation on **all amateur frequencies above 30 MHz**.

For Sally's use case, the relevant bands:

| Band | Frequencies | Notes |
|---|---|---|
| **2 m** | 144–148 MHz | The workhorse for vehicle-to-vehicle voice. 25–50 W mobile + magnetic-mount roof whip = 5–30 km simplex, line-of-sight. Repeaters all over BC extend this dramatically. |
| **70 cm** | 430–450 MHz | Pairs nicely with 2 m — dual-band mobiles cover both. Better around buildings, slightly worse over distance. |
| **6 m, 1.25 m, 33 cm, 23 cm** | various | Less commonly used; nice to have access |

**Basic with Honours** (80%+ on the same exam) **unlocks HF** — long-distance shortwave. Worth aiming for if you're studying anyway; the extra 10 percentage points isn't a meaningful extra effort, and HF means you can talk to other amateurs hundreds or thousands of km away. Not necessary for camper-to-camper.

**Advanced Qualification** (separate 50-question exam): adds the ability to build your own transmitters, sponsor a club station, run higher power, and operate your own repeater. Not needed for what we're doing.

## Recommended rig for Sally

| Component | Suggested model | Approx CAD | Notes |
|---|---|---|---|
| Dual-band mobile (2 m / 70 cm) | **Anytone AT-578UV** | $280 | Cheap, capable, well-supported. Or Yaesu FT-7900R (~$400, classic Japanese build) / Icom IC-2730A (~$450). |
| Antenna | **Comet CA-2x4SR** or **Diamond NR770HB** dual-band mobile whip on an **NMO magnetic mount** | $80–120 + mount $40 | NMO is the de-facto mobile-radio mount; magnetic mounts are non-destructive on Sally's roof |
| Coax | LMR-240 or RG-58, ~15 ft, with NMO-to-PL259 ends | $30 | Run from roof through a window seal or grommet to the radio |
| Power | Direct from house battery, fused at 15 A | — | Mobile radios run at 13.8 V — Sally's house battery is in spec. Hard-wire, don't depend on shore power. |
| Mounting | Under-dash or on the engine doghouse | — | Most mobiles ship with a remote-head kit if dash space is tight |

Total for one rig: **~$430–550 CAD**. Both campers need their own rig + license.

## The other camper

For two-way to work, the other camper also needs the Basic Qualification + a 2 m / 70 cm mobile. Study together — RAC and most clubs welcome study buddies, and the exam can be written at the same examiner session.

## Coordination

Once both campers are licensed:

- Agree on a **simplex frequency** in the 2 m calling band (e.g. 146.520 MHz is the national simplex calling channel in North America — agree to QSY off it to a less-used simplex frequency for your actual conversation)
- Or use the **local BC repeater network** (huge in BC — repeaters on most major peaks). [BCFM Communications Association](https://bcfm.bc.ca/) and [RAC repeater directory](https://www.rac.ca/repeater-directory/) list them. Use the repeater that covers wherever you're camping.
- For situations where one camper has driven ahead and there's a ridge between you, repeaters bridge the line-of-sight problem cleanly.

## Why this is *strictly better* than the FM-band hack

| | FM-band hack (illegal) | Amateur 2 m mobile (legal) |
|---|---|---|
| Range simplex | ~few hundred ft if you stayed compliant; "useful" range only if you broke the law | 5–30 km |
| Range via repeaters | Not a thing — FM broadcast doesn't have repeaters | Full-valley, often beyond |
| Legal status | Unlicensed broadcasting — fines, seizure, possible criminal liability | Fully licensed |
| One-time cost | $40 + risk | ~$500 + a weekend of study |
| Lifetime cost | Risk continues every transmission | Zero — license is free and permanent |
| Audio quality | FM-broadcast quality (good) | FM narrow voice (excellent for speech, designed for it) |
| Community | None — you're alone | Active BC amateur community, repeaters everywhere, emergency comms training opportunities |

## Roadmap

1. **Study + write Basic Qualification.** Both camper drivers, ideally together. Aim for Basic with Honours.
2. **Buy mobile rigs.** Identical model on both campers makes troubleshooting easier.
3. **Install rig + NMO mount + roof whip + 12 V hard-wire** in Sally. The other camper does the same.
4. **Program the repeater list** for the regions you camp in (BCFM, valley repeaters, simplex calling).
5. **Field test:** drive separate vehicles 5 km apart, confirm simplex contact. 50 km apart, confirm via repeater.

## Next action

Bookmark [HamStudy.org](https://hamstudy.org/) and the [ISED exam generator](https://ised-isde.canada.ca/site/amateur-radio-operator-certificate-services/en/amateur-radio-exam-generator). Pick a target exam date (a Saturday club night is typical) and start the question bank. Aim for Basic with Honours — same effort, much bigger reward.

## See also

- [`README.md`](README.md) — kid-grade FRS handhelds stay; amateur is the adult driver-to-driver upgrade
- [`subsystems/audio/fm-broadcast.md`](../audio/fm-broadcast.md) — Sally's own FM transmitter, scoped strictly to BETS-1 cabin/boat-range music broadcast (never voice channel)
