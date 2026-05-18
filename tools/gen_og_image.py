#!/usr/bin/env python3
"""Generate a static Open Graph image for the site.

Output: dist/og.png at 1200×630 (FB/Twitter card spec).
Idempotent — overwrites if present.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import site_queries  # noqa: E402

W, H = 1200, 630
BG = (245, 241, 232)        # cream — matches site --bg-cream-ish
INK = (26, 24, 21)          # near-black
GOLD = (200, 168, 90)       # site --gold
MUTED = (122, 118, 108)     # secondary text
SERIF = "/System/Library/Fonts/Supplemental/Georgia.ttf"
SERIF_B = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
MONO = "/System/Library/Fonts/Menlo.ttc"


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _stats(db_path: str = "data/streets.db") -> dict:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    out = {
        "total_streets": c.execute(
            "SELECT COUNT(*) FROM streets_dedup WHERE is_numeric=0"
        ).fetchone()[0],
        "total_uats": c.execute(
            "SELECT COUNT(DISTINCT siruta) FROM streets_dedup"
        ).fetchone()[0],
        "total_judete": c.execute(
            "SELECT COUNT(DISTINCT judet) FROM streets_dedup"
        ).fetchone()[0],
    }
    conn.close()
    return out


def main() -> None:
    out = ROOT / "dist" / "og.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    stats = _stats()

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Gold rule top
    draw.rectangle([(0, 0), (W, 6)], fill=GOLD)

    # Brand mark
    eyebrow = _font(MONO, 22)
    draw.text((72, 64), "◆ CUM NE NUMIM STRĂZILE", font=eyebrow, fill=INK)

    # Headline (two lines, serif)
    h1 = _font(SERIF_B, 60)
    draw.text((72, 130), "Cine se ascunde în spatele numelor", font=h1, fill=INK)
    draw.text((72, 200), "de străzi din România?", font=h1, fill=INK)

    # Subhead
    sub = _font(SERIF, 24)
    draw.text((72, 290),
              "Personalități, natură, ideologie, locuri — date din",
              font=sub, fill=MUTED)
    draw.text((72, 320),
              "registrul Autorității Electorale Permanente.",
              font=sub, fill=MUTED)

    # Stats band
    yband = 380
    draw.rectangle([(72, yband), (W - 72, yband + 150)], fill=INK)

    num_font = _font(SERIF_B, 56)
    lbl_font = _font(MONO, 16)

    total = stats["total_streets"]
    uats = stats["total_uats"]
    judete = stats["total_judete"]

    items = [
        (f"{total:,}".replace(",", "."), "străzi inventariate"),
        (f"{uats:,}".replace(",", "."), "localități"),
        (f"{judete}", "județe + B"),
    ]
    col_w = (W - 144) // 3
    for i, (n, lbl) in enumerate(items):
        x = 72 + i * col_w + 28
        draw.text((x, yband + 28), n, font=num_font, fill=(255, 255, 255))
        draw.text((x, yband + 104), lbl.upper(), font=lbl_font, fill=GOLD)

    # Footer line
    foot = _font(MONO, 18)
    draw.text((72, H - 64), "strazi.gov2.ro", font=foot, fill=INK)

    img.save(out, "PNG", optimize=True)
    print(f"  → {out}  ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
