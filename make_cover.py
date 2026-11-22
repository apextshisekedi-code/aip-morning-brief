#!/usr/bin/env python3
"""Generate cover.jpg (3000x3000) if it doesn't exist. Replace cover.jpg with your own art any time."""
import glob
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "cover.jpg"


def font(size, bold=True):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for p in glob.glob(f"/usr/share/fonts/**/{name}", recursive=True):
        return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def main():
    if OUT.exists():
        print("cover.jpg exists; keeping it")
        return
    S = 3000
    img = Image.new("RGB", (S, S), (11, 27, 51))
    d = ImageDraw.Draw(img)
    for i, h in enumerate([0.25, 0.45, 0.35, 0.6, 0.5, 0.75, 0.55, 0.85]):
        x = 330 + i * 300
        top = int(2350 - h * 900)
        d.rectangle([x, top, x + 170, 2350], fill=(255, 184, 0) if i == 7 else (0, 168, 150))
    d.text((330, 330), "THE AIP", font=font(300), fill=(255, 255, 255))
    d.text((330, 660), "MORNING BRIEF", font=font(250), fill=(255, 255, 255))
    d.text((330, 1000), "Infrastructure capex · SaaS · Strategy", font=font(105, False), fill=(170, 190, 215))
    d.text((330, 2500), "DAILY  ·  6AM", font=font(140), fill=(255, 184, 0))
    img.save(OUT, quality=90)
    print("cover.jpg generated")


if __name__ == "__main__":
    main()
