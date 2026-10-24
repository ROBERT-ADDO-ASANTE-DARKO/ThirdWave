"""
vlm_client.py — backend port of streamlit_app/vlm_client.py's real
Anthropic Messages API calls for AI-drafted flood report descriptions and
annotated depth-estimate images. Logic is unchanged from the Streamlit
version (including its validated bounding-box accuracy, see that file's
docstring) -- only the .env lookup differs, see below.

Design: the citizen stays in control. This module only ever produces a
DRAFT -- the calling endpoint/client must treat the result as editable
and never auto-submit it. See routers/reports.py's POST /reports/draft.

Duplicated from streamlit_app/vlm_client.py rather than imported, same
reasoning as clustering.py/news_corroboration.py: this backend must stay
runnable without a Streamlit dependency.
"""

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageOps

# ANTHROPIC_API_KEY/ANTHROPIC_WORKSPACE_ID live in the ThirdWave project
# root .env (same file streamlit_app/vlm_client.py reads) -- backend/.env
# holds backend-specific secrets (Firebase, the officer key) instead of
# duplicating this one, so there's a single place these credentials live.
load_dotenv(Path(__file__).parent.parent / ".env")

MODEL = "claude-sonnet-5"
HAZARD_TYPES = ["flash_flood", "urban_flood", "river_flood"]

SYSTEM_PROMPT = """You are helping draft a citizen flood report from a photo, for a flood early-warning \
system in Accra, Ghana. Look at the image and write a short, factual, plain-language description of what \
it shows, suitable for a citizen to review and edit before submitting an official report.

Rules:
- Describe only what's visibly in the photo. Do not guess at severity you can't see.
- If the photo does NOT clearly show flooding (e.g. it's unrelated, unclear, or ambiguous), say so plainly \
instead of inventing flood content.
- Keep the description to 1-2 sentences, written as the citizen would write it (first-person-adjacent, \
plain language, not clinical).
- Suggest ONE hazard_type from exactly this list: flash_flood, urban_flood, river_flood -- or null if the \
photo doesn't support a confident guess.
- If flooding is visible, carefully scan the ENTIRE image for EVERY object of known approximate size that \
could anchor a water-depth estimate (vehicles of any type, doorways, curbs, people, road signs, motorbikes, \
tricycles, storefronts, steps, etc.) -- do not stop at the first one or two you notice; look at all regions \
of the frame including background and edges. For EACH one you can confidently locate, give a PIXEL bounding \
box [x_min, y_min, x_max, y_max] for the exact image dimensions given to you, plus the approximate waterline \
y-coordinate in pixels near it. There is no cap on how many you report -- list every one you're actually \
confident about, whether that's one or a dozen. Use the full set together to reason about water depth (they \
should agree with each other; note in "note" if they visibly disagree). If you can't confidently identify \
any reference object, or there's no flooding, leave reference_objects empty and depth_estimate_m null -- do \
not guess.

Respond with ONLY a JSON object, no other text, in this exact shape:
{"shows_flooding": true or false, "description": "...", "suggested_hazard_type": "flash_flood" | "urban_flood" | "river_flood" | null, "note": "brief note on confidence or what's unclear, if anything", "depth_estimate_m": {"low": 0.0, "high": 0.0} or null, "reference_objects": [{"label": "...", "box_px": [x1, y1, x2, y2], "waterline_y_px": 0}]}"""


class VLMError(Exception):
    pass


def _normalize_orientation(image_bytes: bytes) -> bytes:
    """Bakes in EXIF orientation (common on phone camera photos) -- see
    streamlit_app/vlm_client.py's identical function for why."""
    im = Image.open(io.BytesIO(image_bytes))
    im = ImageOps.exif_transpose(im)
    if im.mode != "RGB":
        im = im.convert("RGB")
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=92)
    return out.getvalue()


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise VLMError("No ANTHROPIC_API_KEY found (checked ThirdWave/.env and environment).")
    workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
    return anthropic.Anthropic(api_key=api_key, default_headers=headers)


def describe_flood_photo(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """Same as streamlit_app/vlm_client.py's function of the same name --
    see that module's docstring for the full behavior contract. Raises
    VLMError on any failure; caller must handle this and fall back to
    manual entry, never block submission on this failing."""
    client = _get_client()

    image_bytes = _normalize_orientation(image_bytes)
    media_type = "image/jpeg"
    width, height = Image.open(io.BytesIO(image_bytes)).size
    b64_image = base64.b64encode(image_bytes).decode("ascii")

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_image}},
                    {"type": "text", "text": f"Image dimensions: width={width} height={height}. "
                                              "Draft a flood report description for this photo, per your instructions."},
                ],
            }],
        )
    except Exception as exc:
        raise VLMError(f"API call failed: {exc}") from exc

    raw_text = "".join(block.text for block in response.content if hasattr(block, "text"))
    try:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
        result = json.loads(cleaned.strip())
    except (json.JSONDecodeError, IndexError) as exc:
        raise VLMError(f"Could not parse model response as JSON: {raw_text[:200]}") from exc

    if result.get("suggested_hazard_type") not in HAZARD_TYPES + [None]:
        result["suggested_hazard_type"] = None

    valid_objects = []
    for obj in result.get("reference_objects") or []:
        box = obj.get("box_px")
        if (isinstance(box, list) and len(box) == 4
                and 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
            valid_objects.append(obj)
    result["reference_objects"] = valid_objects

    return result


def annotate_image(image_bytes: bytes, vlm_result: dict) -> bytes | None:
    """Same as streamlit_app/vlm_client.py's function of the same name.
    Returns None (not a placeholder image) when there's nothing
    trustworthy to draw."""
    objects = vlm_result.get("reference_objects") or []
    if not objects:
        return None

    image_bytes = _normalize_orientation(image_bytes)
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(im)
    line_w = max(3, im.width // 400)
    font_size = max(16, im.width // 45)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    placed_label_boxes: list[tuple[float, float, float, float]] = []

    def _overlaps(a, b) -> bool:
        return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]

    for obj in objects:
        box = obj["box_px"]
        draw.rectangle(box, outline=(255, 60, 60), width=line_w)
        label = obj.get("label", "")
        if label:
            candidates = [
                max(0, box[1] - font_size - line_w),
                min(im.height - font_size, box[3] + line_w),
                max(0, box[1] - 2 * (font_size + line_w)),
                min(im.height - font_size, box[3] + font_size + 2 * line_w),
            ]
            tx = min(box[0], im.width - draw.textlength(label, font=font) - 8)
            tx = max(0, tx)
            ty = candidates[0]
            for cy in candidates:
                cbox = draw.textbbox((tx, cy), label, font=font)
                if not any(_overlaps(cbox, placed) for placed in placed_label_boxes):
                    ty = cy
                    break
            else:
                ty = candidates[0]

            tbox = draw.textbbox((tx, ty), label, font=font)
            draw.rectangle((tbox[0] - 4, tbox[1] - 2, tbox[2] + 4, tbox[3] + 2), fill=(255, 60, 60))
            draw.text((tx, ty), label, fill=(255, 255, 255), font=font)
            placed_label_boxes.append((tbox[0] - 4, tbox[1] - 2, tbox[2] + 4, tbox[3] + 2))
        wl_y = obj.get("waterline_y_px")
        if isinstance(wl_y, (int, float)):
            draw.line([(0, wl_y), (im.width, wl_y)], fill=(255, 220, 0), width=max(2, line_w // 2))

    depth = vlm_result.get("depth_estimate_m")
    if depth:
        caption = f"Est. depth: {depth['low']:.1f}-{depth['high']:.1f}m"
        band_h = font_size + 16
        draw.rectangle([0, 0, im.width, band_h], fill=(11, 37, 69))
        draw.text((10, 8), caption, fill=(255, 255, 255), font=font)

    out = io.BytesIO()
    im.save(out, format="JPEG", quality=85)
    return out.getvalue()
