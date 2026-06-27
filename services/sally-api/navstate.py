"""navstate.py — pure nav-tick logic, shared by scripts/nav-tick.py and the API (W2 GPS-loss
overlay) and unit-tested off the Pi (test_navstate.py). No I/O, no config — like waypoints.py.

`compute_nav()` turns the previous nav-state + a fresh gpsd fix into the new nav-state read-model
(fix-age + frozen last-known position). `should_write()` is the SD-sparing write-gate so the tick
only touches the card on a meaningful change (fix flip, a coarser seconds-since-fix bucket, real
movement, or a periodic heartbeat) rather than every few seconds forever.
"""
import waypoints

SCHEMA_VERSION = 1


def compute_nav(prev, fix, now, first_ts):
    """New nav-state from the previous one + a gpsd fix. `now`/`first_ts` are injected (epoch s).

    - With a fix: secondsSinceFix=0, lastFixTs=now, lastKnown=current position.
    - Lost after a fix: count up from the last fix; keep the FROZEN last-known position.
    - Never fixed this run: count up from first_ts; no last-known.
    """
    now = int(now)
    if fix.get("fix") and fix.get("lat") is not None:
        return {"schemaVersion": SCHEMA_VERSION, "ts": now, "fix": True, "hadFix": True,
                "lastFixTs": now, "secondsSinceFix": 0,
                "lastKnown": {"lat": fix["lat"], "lon": fix["lon"],
                              "speed_kmh": fix.get("speed_kmh"),
                              "heading": fix.get("heading"), "alt_m": fix.get("alt_m")}}
    last_fix_ts = prev.get("lastFixTs")
    since = (now - int(last_fix_ts)) if last_fix_ts else (now - int(first_ts))
    return {"schemaVersion": SCHEMA_VERSION, "ts": now, "fix": False,
            "hadFix": bool(prev.get("hadFix")), "lastFixTs": last_fix_ts,
            "secondsSinceFix": since, "lastKnown": prev.get("lastKnown")}


def should_write(prev, new, last_write_ts, move_m, healthy_s, bucket_s=5):
    """SD-sparing write-gate: write on a fix-state flip; while lost, when the secondsSinceFix
    bucket advances (so the overlay counter stays current); while fixed, on real movement or a
    periodic heartbeat. Returns True when `new` should be persisted."""
    if bool(prev.get("fix")) != bool(new.get("fix")):
        return True
    if not new.get("fix"):
        return (int((prev.get("secondsSinceFix") or 0) // bucket_s)
                != int((new.get("secondsSinceFix") or 0) // bucket_s))
    if (int(new["ts"]) - int(last_write_ts or 0)) >= healthy_s:
        return True
    pk, nk = prev.get("lastKnown") or {}, new.get("lastKnown") or {}
    if pk.get("lat") is None or nk.get("lat") is None:
        return True
    return waypoints.haversine_km(pk["lat"], pk["lon"], nk["lat"], nk["lon"]) * 1000.0 >= move_m
