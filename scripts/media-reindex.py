#!/usr/bin/env python3
"""media-reindex.py — rebuild the catalog.json read-model from per-item sidecars.

Sidecars (one JSON per item, on the HDD with the media) are the source of truth.
catalog.json is a derived cache that sally-api loads and slices to serve
/api/media?type=trips, /api/collections/<id> and /api/photos. It lives on the Pi's
local disk (not exFAT) and is rewritten atomically under an flock so a concurrent
worker + API never see a half-written file.

Shape:
  { schemaVersion, generated,
    collections: [ {id,kind,title,poster,itemCount,videoCount,photoCount,
                    dateStart,dateEnd,place?,detailUrl} ],
    items:  { "<collectionId>": [ item, ... ] },   # item = browse fields, url/poster prefixed
    photos: [ {id,url,poster,captureDatetime,gps?,collectionId,title?}, ... ] }

URLs are stored as "/media/<relpath>" — the fixed route; the Roku prepends host/scheme.

Env (all overridable; N100 migration is a path change):
  SIDECAR_DIR   per-item sidecars     (default /mnt/usb/home/catalog/items)
  MEDIA_ROOT    served library root   (default /mnt/usb/home/library) — also holds trip.json
  CATALOG_JSON  output read-model     (default /var/lib/sally/catalog.json)
"""
import fcntl
import glob
import json
import os
import sys
import time

SIDECAR_DIR = os.environ.get("SIDECAR_DIR", "/mnt/usb/home/catalog/items")
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", "/mnt/usb/home/library")
CATALOG_JSON = os.environ.get("CATALOG_JSON", "/var/lib/sally/catalog.json")
# Canonical trip store (SD card) written by sally-api's trip-entry form. Source of
# truth for trip metadata; wins over the legacy per-collection HDD trip.json files.
TRIPS_JSON = os.environ.get("TRIPS_JSON", "/var/lib/sally/trips.json")
# Past-trip geotagged photos -> map pins (read by sally-api's "photos" map layer).
PHOTO_POI_JSON = os.environ.get("PHOTO_POI_JSON", "/var/lib/sally/photo-poi.json")


def media_url(relpath):
    return "/media/" + relpath.lstrip("/") if relpath else None


def load_sidecars():
    items = []
    for p in glob.glob(os.path.join(SIDECAR_DIR, "*.json")):
        try:
            with open(p) as f:
                items.append(json.load(f))
        except (ValueError, OSError):
            continue  # skip a single bad sidecar; never fail the whole reindex
    return items


def load_trip_meta():
    """collectionId -> trip metadata (title, place, cover, dates).

    Reconciles two sources: the legacy per-collection HDD trip.json files (kept for
    backward-compat / hand edits) and the canonical SD trips.json the dashboard's
    trip-entry form writes. The SD store WINS per collection — it removes a read
    dependency on the failing HDD and lets trip entry create a collection's metadata
    before any photo lands there.
    """
    meta = {}
    for p in glob.glob(os.path.join(MEDIA_ROOT, "trips", "*", "trip.json")):
        try:
            with open(p) as f:
                t = json.load(f)
            if t.get("id"):
                meta[t["id"]] = t
        except (ValueError, OSError):
            continue
    try:
        with open(TRIPS_JSON) as f:
            store = json.load(f)
        for cid, t in (store.get("trips") or {}).items():
            if t.get("id"):
                meta[cid] = {**meta.get(cid, {}), **t}  # SD store overrides HDD
    except (ValueError, OSError):
        pass
    return meta


def browse_item(sc):
    """Project a sidecar to the fields the Roku browse/play view needs."""
    return {
        "id": sc.get("id"),
        "type": sc.get("type"),
        "title": sc.get("title"),
        "url": media_url(sc.get("mediaPath")),
        "poster": media_url(sc.get("posterPath")),
        "durationSec": sc.get("durationSec"),
        "codec": sc.get("codec"),
        "width": sc.get("width"),
        "height": sc.get("height"),
        "captureDatetime": sc.get("captureDatetime"),
        "gps": sc.get("gps"),
        "uploader": sc.get("uploader"),
    }


def build(sidecars, trips):
    by_coll = {}          # id -> list of sidecars
    coll_info = {}        # id -> {kind, title}
    for sc in sidecars:
        c = sc.get("collection") or {}
        cid = c.get("id") or "unsorted"
        by_coll.setdefault(cid, []).append(sc)
        coll_info.setdefault(cid, {"kind": c.get("kind") or "bucket",
                                   "title": c.get("title") or cid})

    collections, items, photos = [], {}, []
    for cid, scs in sorted(by_coll.items()):
        scs.sort(key=lambda s: s.get("captureDatetime") or "")
        dates = [s.get("captureDatetime") for s in scs if s.get("captureDatetime")]
        vids = [s for s in scs if s.get("type") == "video"]
        pics = [s for s in scs if s.get("type") == "photo"]
        tmeta = trips.get(cid, {})

        # Cover poster: trip.json cover > first item poster.
        cover = media_url(tmeta.get("coverPath")) if tmeta.get("coverPath") else None
        if not cover and scs:
            cover = media_url(scs[0].get("posterPath"))

        collections.append({
            "id": cid,
            "kind": coll_info[cid]["kind"],
            "title": tmeta.get("title") or coll_info[cid]["title"],
            "poster": cover,
            "itemCount": len(scs),
            "videoCount": len(vids),
            "photoCount": len(pics),
            "dateStart": tmeta.get("dateStart") or (min(dates)[:10] if dates else None),
            "dateEnd": tmeta.get("dateEnd") or (max(dates)[:10] if dates else None),
            "place": tmeta.get("place"),
            "detailUrl": "/api/collections/" + cid,
        })
        items[cid] = [browse_item(s) for s in scs]
        for s in pics:
            photos.append({
                "id": s.get("id"),
                "url": media_url(s.get("mediaPath")),
                "poster": media_url(s.get("posterPath")),
                "captureDatetime": s.get("captureDatetime"),
                "gps": s.get("gps"),
                "collectionId": cid,
                "title": s.get("title"),
            })

    # Newest collection first; photos newest-first.
    collections.sort(key=lambda c: c.get("dateStart") or "", reverse=True)
    photos.sort(key=lambda p: p.get("captureDatetime") or "", reverse=True)
    return {
        "schemaVersion": 1,
        "generated": int(time.time()),
        "collections": collections,
        "items": items,
        "photos": photos,
    }


def build_photo_poi(photos):
    """Flatten catalog photos that carry a GPS fix into map pins, deduped to ~11 m so a photo
    burst at one spot becomes a single pin (the renderer's POI_CAP handles the rest). Built here,
    piggybacked on the catalog rebuild, since the catalog only changes on media ingest."""
    out, seen = [], set()
    for p in photos:
        g = p.get("gps") or {}
        lat, lon = g.get("lat"), g.get("lon")
        if lat is None or lon is None:
            continue
        key = (round(lat, 4), round(lon, 4))
        if key in seen:
            continue
        seen.add(key)
        out.append({"lat": round(lat, 6), "lon": round(lon, 6),
                    "title": p.get("title"),
                    "thumbUrl": p.get("poster") or p.get("url"),
                    "collectionId": p.get("collectionId"),
                    "capturedTs": p.get("captureDatetime")})
    return {"schemaVersion": 1, "generated": int(time.time()), "photos": out}


def prune(obj):
    if isinstance(obj, dict):
        return {k: prune(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [prune(v) for v in obj]
    return obj


def _atomic(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lock = path + ".lock"
    with open(lock, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(obj, f, indent=2, sort_keys=True)
        os.replace(tmp, path)  # atomic
        fcntl.flock(lf, fcntl.LOCK_UN)


def main():
    catalog = prune(build(load_sidecars(), load_trip_meta()))
    _atomic(CATALOG_JSON, catalog)
    photo_poi = prune(build_photo_poi(catalog["photos"]))
    _atomic(PHOTO_POI_JSON, photo_poi)
    print("reindexed %d collection(s), %d photo(s), %d photo-poi -> %s"
          % (len(catalog["collections"]), len(catalog["photos"]),
             len(photo_poi["photos"]), PHOTO_POI_JSON))


if __name__ == "__main__":
    sys.exit(main())
