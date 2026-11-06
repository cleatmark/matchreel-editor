#!/usr/bin/env python3
"""Generate generic placeholder crests: Home FC, Guest FC and two league badges (League A / League B).

  python tools/pipeline/make_placeholder_logos.py [--out shared/team_logos]

Writes home_fc.png, guest_fc.png, league_a.png, league_b.png (512x512, transparent) and a metadata.json listing them.
They are the defaults the example config points at, so the editor works out of the box; replace them with real crests any time.
"""
import argparse
import json
import os

from PIL import Image, ImageDraw, ImageFont

S = 512
FONTS = ["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf", "Helvetica.ttc"]


def font(size):
    for f in FONTS:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def centered(d, text, cy, size, fill):
    f = font(size)
    box = d.textbbox((0, 0), text, font=f)
    d.text(((S - (box[2] - box[0])) / 2 - box[0], cy - (box[3] - box[1]) / 2 - box[1]), text, font=f, fill=fill)


def shield(d, main, trim, text, sub=None):
    pts = [(64, 48), (448, 48), (448, 256), (400, 360), (256, 464), (112, 360), (64, 256)]
    d.polygon(pts, fill=trim)
    inner = [(88, 72), (424, 72), (424, 248), (384, 342), (256, 436), (128, 342), (88, 248)]
    d.polygon(inner, fill=main)
    d.rectangle((88, 72, 424, 128), fill=trim)
    centered(d, text, 252, 118, "white")
    if sub:
        centered(d, sub, 100, 40, main)


def badge(path, shape, main, trim, letter):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if shape == "circle":
        d.ellipse((40, 40, 472, 472), fill=trim)
        d.ellipse((72, 72, 440, 440), fill=main)
    else:
        hexa = lambda r: [(256 + r * x, 256 + r * y) for x, y in [(0, -1), (0.87, -0.5), (0.87, 0.5), (0, 1), (-0.87, 0.5), (-0.87, -0.5)]]
        d.polygon(hexa(230), fill=trim)
        d.polygon(hexa(195), fill=main)
    centered(d, "LEAGUE", 160, 56, "white")
    centered(d, letter, 300, 230, "white")
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="shared/team_logos")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for name, main_c, trim, text, sub in [("home_fc.png", "#1E3A8A", "#F5B301", "HFC", "HOME"), ("guest_fc.png", "#B91C1C", "#E5E7EB", "GFC", "GUEST")]:
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        shield(ImageDraw.Draw(img), main_c, trim, text, sub)
        img.save(os.path.join(a.out, name))
    badge(os.path.join(a.out, "league_a.png"), "circle", "#15803D", "#FACC15", "A")
    badge(os.path.join(a.out, "league_b.png"), "hex", "#6D28D9", "#E5E7EB", "B")
    meta = [{"team": t, "filename": f, "filepath": "shared/team_logos/" + f, "size_bytes": os.path.getsize(os.path.join(a.out, f)), "source_url": ""}
            for t, f in [("Home FC", "home_fc.png"), ("Guest FC", "guest_fc.png"), ("League A", "league_a.png"), ("League B", "league_b.png")]]
    with open(os.path.join(a.out, "metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    print("wrote", len(meta), "logos to", a.out)


if __name__ == "__main__":
    main()
