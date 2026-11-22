#!/usr/bin/env python3
"""SallyNet brand-asset pipeline.

Reads the mascot source from images/SallyGenerated.png at the monorepo root (NOT shipped)
and emits Roku-spec variants into ../images/ (referenced by the manifest + screens).

Outputs (channel/images/):
  icon_focus_sd.png   248x186   (paletted)
  icon_focus_hd.png   290x218   (paletted)
  icon_focus_fhd.png  540x405   (paletted)
  splash_sd.jpg       720x480   (progressive q88)
  splash_hd.jpg       1280x720  (progressive q88)
  splash_fhd.jpg      1920x1080 (progressive q90)
  mascot.png          900-wide  (transparent, in-channel Splash/Home hero)

Brand: sunset palette — letterbox/pad on golden-hour gold (#E8A044) to evoke the
mascot's sky.  Run: python3 scripts/generate_brand_assets.py
"""
from __future__ import annotations
import os
from pathlib import Path
from PIL import Image

REPO = Path(__file__).resolve().parents[2]          # roku-channel/
SRC = REPO.parent / "images" / "SallyGenerated.png"  # monorepo root images/
OUT = REPO / "channel" / "images"

GOLD_RGB = (0xE8, 0xA0, 0x44)   # SN_GOLD — splash letterbox + icon padding
CREAM_RGB = (0xFF, 0xF8, 0xE1)  # SN_CREAM


def fit_letterbox(src: Image.Image, w: int, h: int, bg) -> Image.Image:
    canvas = Image.new("RGB", (w, h), bg)
    sw, sh = src.size
    scale = min(w / sw, h / sh)
    nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
    r = src.resize((nw, nh), Image.LANCZOS)
    canvas.paste(r, ((w - nw) // 2, (h - nh) // 2), r if r.mode == "RGBA" else None)
    return canvas


def make_icon(logo: Image.Image, w: int, h: int, inset: float = 0.92) -> Image.Image:
    canvas = Image.new("RGBA", (w, h), GOLD_RGB + (0xFF,))
    target = int(min(w, h) * inset)
    sw, sh = logo.size
    scale = target / max(sw, sh)
    nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
    r = logo.resize((nw, nh), Image.LANCZOS)
    canvas.paste(r, ((w - nw) // 2, (h - nh) // 2), r)
    return canvas.convert("RGB").quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE)


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing mascot source: {SRC} (copy sallyNet/images/SallyGenerated.png there)")
    mascot = Image.open(SRC).convert("RGBA")
    OUT.mkdir(parents=True, exist_ok=True)

    for name, w, h in [("icon_focus_sd.png", 248, 186),
                       ("icon_focus_hd.png", 290, 218),
                       ("icon_focus_fhd.png", 540, 405)]:
        make_icon(mascot, w, h).save(OUT / name, "PNG", optimize=True)

    for name, w, h, q in [("splash_sd.jpg", 720, 480, 88),
                          ("splash_hd.jpg", 1280, 720, 88),
                          ("splash_fhd.jpg", 1920, 1080, 90)]:
        fit_letterbox(mascot, w, h, GOLD_RGB).save(
            OUT / name, "JPEG", quality=q, optimize=True, progressive=True)

    # In-channel hero: transparent mascot, max 900 wide.
    hero = mascot.copy()
    if hero.width > 900:
        hero = hero.resize((900, int(hero.height * 900 / hero.width)), Image.LANCZOS)
    hero.save(OUT / "mascot.png", "PNG", optimize=True)

    print(f"{'asset':<24}{'bytes':>10}")
    for p in sorted(OUT.glob("*")):
        print(f"{p.name:<24}{os.path.getsize(p):>10}")


if __name__ == "__main__":
    main()
