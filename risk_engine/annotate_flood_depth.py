"""
annotate_flood_depth.py — Render the VLM's depth-estimation reasoning as
visual annotations on the source photo: boxes around the reference objects
used (vehicle rocker panels / wheels), the inferred waterline, and the
resulting depth estimate.

The reference-object coordinates below were located by visual inspection
(this IS the "vision-language model" step -- Claude viewing the image
directly and identifying pixel regions), not a trained object detector.
That's consistent with the zero-shot methodology this whole exercise is
demonstrating (FloodVision / FloodDepth-GPT-style reasoning), not a
production CV pipeline.

Input:  data/Flooding_Accra_6.jpg (CC BY-SA 4.0, Wikimedia Commons user Fquasie)
Output: data/Flooding_Accra_6_annotated.jpg
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
SRC = HERE / "data" / "Flooding_Accra_6.jpg"
OUT = HERE / "data" / "Flooding_Accra_6_annotated.jpg"

# Reference objects, located by visual inspection on the displayed 2000x1333
# rendering, scaled to the original 5184x3456 image (factor 2.592).
SCALE = 5184 / 2000

REGIONS = {
    "teal sedan (rocker-panel ref)": {"box": (770, 345, 1025, 490), "color": (79, 195, 247)},
    "orange hatchback (rocker-panel ref)": {"box": (1145, 345, 1405, 495), "color": (255, 138, 60)},
    "white pickup (wheel/clearance ref)": {"box": (10, 325, 410, 510), "color": (230, 237, 243)},
}

WATERLINE_Y_DISPLAY = 486  # approx contact line between vehicle bodies and water
RAPIDS_BOX_DISPLAY = (520, 950, 1950, 1230)  # turbulent channel, deeper flow

DEPTH_LABEL = "Estimated depth at crossing: 0.4-0.6m\n(rocker-panel line; rapids channel likely deeper)"


def to_orig(box_display):
    return tuple(int(v * SCALE) for v in box_display)


def main() -> None:
    im = Image.open(SRC).convert("RGB")
    draw = ImageDraw.Draw(im, "RGBA")

    try:
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        font_md = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 38)
    except Exception:
        font_lg = ImageFont.load_default()
        font_md = ImageFont.load_default()

    line_w = int(6 * SCALE / 2.6)  # keep stroke width sane at full res

    # Reference object boxes
    for label, spec in REGIONS.items():
        box = to_orig(spec["box"])
        color = spec["color"]
        draw.rectangle(box, outline=color + (255,), width=line_w)
        tx, ty = box[0], box[1] - int(56 * SCALE / 2.6)
        text_bbox = draw.textbbox((tx, ty), label, font=font_md)
        pad = 8
        draw.rectangle((text_bbox[0] - pad, text_bbox[1] - pad, text_bbox[2] + pad, text_bbox[3] + pad),
                        fill=(13, 17, 23, 210))
        draw.text((tx, ty), label, font=font_md, fill=color + (255,))

    # Waterline (extended across the frame at the reference contact height)
    wl_y = int(WATERLINE_Y_DISPLAY * SCALE)
    draw.line([(0, wl_y), (im.width, wl_y)], fill=(255, 255, 255, 200), width=max(3, line_w // 2))
    wl_label = "Inferred waterline (vehicle rocker-panel contact)"
    lb_box = draw.textbbox((20, wl_y + 10), wl_label, font=font_md)
    pad = 8
    draw.rectangle((lb_box[0] - pad, lb_box[1] - pad, lb_box[2] + pad, lb_box[3] + pad), fill=(13, 17, 23, 210))
    draw.text((20, wl_y + 10), wl_label, font=font_md, fill=(255, 255, 255, 255))

    # Rapids / deeper-flow channel
    rb = to_orig(RAPIDS_BOX_DISPLAY)
    draw.rectangle(rb, outline=(239, 83, 80, 255), width=line_w)
    rlabel = "Turbulent channel -- likely deeper than rocker-panel line"
    rl_box = draw.textbbox((rb[0], rb[1] - int(56 * SCALE / 2.6)), rlabel, font=font_md)
    draw.rectangle((rl_box[0] - pad, rl_box[1] - pad, rl_box[2] + pad, rl_box[3] + pad), fill=(13, 17, 23, 210))
    draw.text((rb[0], rb[1] - int(56 * SCALE / 2.6)), rlabel, font=font_md, fill=(239, 83, 80, 255))

    # Summary panel, top-left
    panel = (20, 20, 20 + int(1300 * SCALE / 2.6), 20 + int(160 * SCALE / 2.6))
    draw.rectangle(panel, fill=(13, 17, 23, 225), outline=(212, 160, 23, 255), width=line_w // 2)
    draw.text((panel[0] + 24, panel[1] + 20), "Zero-shot VLM flood-depth estimate", font=font_lg, fill=(212, 160, 23, 255))
    draw.text((panel[0] + 24, panel[1] + 80), DEPTH_LABEL, font=font_md, fill=(230, 237, 243, 255))

    # Attribution (license requirement -- CC BY-SA 4.0)
    attr = "Photo: Fquasie / Wikimedia Commons, CC BY-SA 4.0 -- depicts 2022-06-18 Accra flooding (not the 2015/2023 Circle events)"
    ab_box = draw.textbbox((20, im.height - int(70 * SCALE / 2.6)), attr, font=font_md)
    draw.rectangle((ab_box[0] - pad, ab_box[1] - pad, ab_box[2] + pad, ab_box[3] + pad), fill=(13, 17, 23, 210))
    draw.text((20, im.height - int(70 * SCALE / 2.6)), attr, font=font_md, fill=(139, 148, 158, 255))

    # Save at a reasonable size (full-res annotation, then downscale for a manageable file)
    im.thumbnail((2400, 2400 * im.height // im.width))
    im.save(OUT, quality=90)
    print(f"Saved -> {OUT}")


if __name__ == "__main__":
    main()
