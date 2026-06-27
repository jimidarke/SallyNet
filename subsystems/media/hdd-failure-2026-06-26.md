# Media HDD failure — diagnosis (2026-06-26)

> **✅ RESOLVED 2026-06-27 — the HDD was replaced with a Crucial BX500 1 TB SSD** (ext4, mounted at
> `/mnt/usb` by UUID with `nofail`). The media library was **not migrated — it's re-encoded from
> source**; the user's movies/TV were preserved on the SSD, and the SD-card read-models were
> untouched. After the swap the Pi boots clean (`get_throttled = 0x0`). The diagnosis below is kept
> as the historical record of the failure that prompted the swap. Current storage state:
> `docs/current-state.md`.

Findings from validating the photo-upload pipeline end-to-end for the first time on real
data. Short version: **the pipeline software works (it failed safe); the HDD underneath it is
physically failing.** SMART can't be read through the enclosure to grade exactly how bad.

## What triggered it

A test photo (`1000018359.jpg`, 2.3 MB) was uploaded via `POST /api/upload` (`uploader: Jimi`,
`trip: unsorted`). It landed correctly in `/mnt/usb/home/inbox/2026-06-26T21-48-48--c563/`
with its `upload.json`, waiting for the nightly encode timer. Running ingest manually
(`/opt/sally/media/media-ingest.sh --once`) to validate the chain produced:

```
==> batch 2026-06-26T21-48-48--c563
mkdir: cannot create directory '/mnt/usb/home/library/unsorted/photos': Input/output error
 fail encode failed for 1000018359.jpg (rc=1)
 fail batch 2026-06-26T21-48-48--c563 moved to failed/
reindexed 0 collection(s), 0 photo(s)
```

## Root cause: physical media failure (SCSI MEDIUM ERROR)

`dmesg` at the moment of the run:

```
sd 0:0:0:0: [sda] Sense Key : 0x3 [current]          # 0x3 = MEDIUM ERROR
sd 0:0:0:0: [sda] ASC=0x3 ASCQ=0x0                    # peripheral device write fault
blk_update_request: I/O error, dev sda, sector 319860224 op 0x1:(WRITE) ...
Buffer I/O error on dev sda1, logical block 39982272, lost async page write
```

- The failures are **WRITE** faults (`op 0x1:(WRITE)`, opcode `0x2a` = SCSI WRITE(10)) at
  sectors **319860224–319868160**.
- This is the **same physical band** that first threw an unrecovered **READ** error on
  2026-06-26 (`sector 319863040`, ASC 0x11). So it's **one localized bad region** that now
  fails both reads and writes — not random whole-platter decay.
- The exFAT directory entries that happen to live in that band are now **unreadable**
  (`ls` → `Input/output error`):
  - `home/library/unsorted`
  - `home/library/memories`
  - `home/library/tracks`
  - `home/logs`
- Everything else reads fine: `home/library/trips` (empty) OK, and **`/mnt/usb/media` = 312 GB
  of movies (180 GB) + TV (133 GB) is fully readable.**

Ingest blew up specifically because `trip: unsorted` routed the photo straight into
`library/unsorted/`, which sits on the dead band.

## The pipeline behaved correctly

This is **not a pipeline-code bug.** On the encode failure the worker:
- left **no partial sidecar** and **no half-written media** (explicit rollback in
  `media-ingest.sh::process_file`),
- moved the whole batch to `failed/` with a `.err` marker,
- left `catalog.json` clean at `0 collections / 0 photos`.

**The test photo is intact** at `home/failed/2026-06-26T21-48-48--c563/1000018359.jpg`. The
fail-safe rollback path got its first real-world test and passed.

## SMART is unreadable through the enclosure

`smartmontools` + `exfatprogs` were installed on the Pi (`/sbin/smartctl` works), but the drive
sits behind a **Seagate USB bridge (`0bc2:ab73`, "Seagate RSS LLC")** that **does not support
SAT passthrough**. Every probe (`-d sat`, `sat,16`, `sat,12`, `scsi`, `usbjmicron`, `auto`)
wedges in uninterruptible I/O and only clears via a 60 s kernel command-timeout
(`[sda] timing out command, waited 60s`). The disk survives the probing (media stays
readable), but **reallocated/pending-sector counts cannot be obtained here.**

→ To read SMART, the bare drive must be **shucked and connected via native SATA** (or a
SAT-capable USB adapter). **Do not re-attempt SMART through this enclosure.**

## Verdict: format or replace?

Can't be graded without SMART, but the SMART numbers **wouldn't change the immediate action**:

- A **full destructive-write format** / `badblocks -w` is a legitimate repair *attempt* — it
  forces the drive to remap the bad band to spare sectors. Since the damage is one localized
  band on a disk that otherwise reads 312 GB cleanly, it **might** clear the symptom. A **quick**
  format would not (it only rewrites FS metadata and would re-land on the same band).
- But this is a cheap 2.5" **SMR Seagate ST1000LM037** that has now thrown **both read and
  write** medium errors at the same spot — write-faults specifically suggest a remap was
  *attempted and still failed*. **Do not trust it as the single source of truth for family
  media,** even if a format makes it mountable again. The Phase-3 N100 migration wants a fresh
  (ideally CMR) drive regardless.

## Recommended order of operations

1. **Back up the 312 GB `media/` library now, while it's readable** — this is the only step
   that's unambiguously correct no matter what SMART would have said. Use resumable
   `rsync -a --ignore-errors --partial` so the one bad band can't abort the whole copy. Target
   TBD (second USB disk on the Pi, or over the WireGuard tunnel).
2. *Then* decide: full-format-test (salvage as scratch only if it passes a clean
   `badblocks -w`), or retire and replace.
3. If SMART grading is wanted, shuck the drive and read it on a machine with native SATA — it
   takes seconds there.

## Mitigations already in place

- `catalog.json` + GPS breadcrumbs live on the **Pi SD card** (`/var/lib/sally/`), off the
  exFAT HDD — so the read-model survives the disk.
- Per-item sidecars (the metadata source of truth) still live on the HDD at
  `home/catalog/items/` — these would be lost with the disk; folded into the backup above.

## Status note — what "verified end-to-end" meant

`subsystems/media/README.md` describes Phase 1 media as "verified end-to-end ... no errors."
That verification was real but used a **generated/synthetic test image**, and the test
artifacts were cleaned up afterward — which is why the catalog now reads `0 collections /
0 photos` and the library is empty. So the happy path *was* exercised once against a generated
file.

What's **new today**: this is the first ingest of a **real guest upload**, and the first to
route into `library/unsorted/` — which now sits on the degraded write band. The HDD has
deteriorated since that earlier test (the original read-error region now also rejects writes).
So the pipeline isn't regressed; the **storage under it has degraded**, and the happy path is
now blocked on hardware rather than code.
