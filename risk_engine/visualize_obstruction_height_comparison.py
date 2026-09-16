"""
visualize_obstruction_height_comparison.py — side-by-side comparison of
building_obstruction_height.py's two runs: the validated Accra pilot
result vs. the confirmed-unreliable Lower Volta basin result. See that
script's docstring for the full method and the validation numbers this
figure illustrates.

Requires both diagnostics to already exist (run building_obstruction_height.py
for each grid first):
    data/building_obstruction_height_diagnostic.png
    data/lower_volta_building_obstruction_height_diagnostic.png

Output: data/building_obstruction_height_comparison.png

Usage
─────
    python3 visualize_obstruction_height_comparison.py
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
PILOT_PNG = HERE / "data" / "building_obstruction_height_diagnostic.png"
LOWER_VOLTA_PNG = HERE / "data" / "lower_volta_building_obstruction_height_diagnostic.png"
PILOT_JSON = HERE / "data" / "building_obstruction_height.json"
LOWER_VOLTA_JSON = HERE / "data" / "lower_volta_building_obstruction_height.json"
OUTPUT = HERE / "data" / "building_obstruction_height_comparison.png"


def _corr(json_path: Path) -> float:
    return json.loads(json_path.read_text())["validation"]["correlation_with_impervious_pct"]


def run():
    for p in (PILOT_PNG, LOWER_VOLTA_PNG):
        if not p.exists():
            raise FileNotFoundError(f"{p} missing -- run building_obstruction_height.py for that grid first")

    pilot_corr = _corr(PILOT_JSON)
    lv_corr = _corr(LOWER_VOLTA_JSON)

    im1 = Image.open(PILOT_PNG).convert("RGB")
    im2 = Image.open(LOWER_VOLTA_PNG).convert("RGB")

    target_h = max(im1.height, im2.height)

    def resize_to_h(im, h):
        w = int(im.width * h / im.height)
        return im.resize((w, h))

    im1 = resize_to_h(im1, target_h)
    im2 = resize_to_h(im2, target_h)

    pad, banner_h = 40, 90
    w = im1.width + im2.width + pad * 3
    h = target_h + banner_h + pad * 2
    canvas = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(canvas)
    try:
        font_b = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        font_s = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except Exception:
        font_b = font_s = ImageFont.load_default()

    draw.text((pad, 15), "CopDEM − FABDEM obstruction-height: validated (pilot) vs. unreliable (Lower Volta)",
              font=font_b, fill=(20, 20, 20))
    draw.text((pad, 52),
              f"Left: Accra pilot, r={pilot_corr:.2f} vs. impervious land cover — a real signal.   "
              f"Right: Lower Volta basin, r={lv_corr:.2f} — dominated by forest/terrain noise near Akosombo, not buildings.",
              font=font_s, fill=(80, 80, 80))

    canvas.paste(im1, (pad, banner_h + pad))
    canvas.paste(im2, (pad * 2 + im1.width, banner_h + pad))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT, quality=95)
    print(f"Saved -> {OUTPUT} ({canvas.size[0]}x{canvas.size[1]})")


if __name__ == "__main__":
    run()
