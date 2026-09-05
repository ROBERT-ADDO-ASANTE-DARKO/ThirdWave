"""
vlm_client.py — real Anthropic Messages API calls for AI-drafted flood
report descriptions and annotated depth-estimate images.

This is real wired integration, not a stub. Earlier VLM work in this
project (image_depth_estimation_poc.json, the Circle/Kaneshie photo
analyses, annotate_flood_depth.py) was Claude reasoning on images directly
in chat, with bounding boxes placed by hand after visual inspection. The
bounding-box return here is a genuinely different, harder capability --
tested against the same validated Circle photo before shipping (see
project chat history): the model's returned waterline (~1250px) came back
within 10px of the hand-placed one (1259px), which is why this was judged
trustworthy enough to automate rather than assumed.

Design: the citizen stays in control. This module only ever produces a
DRAFT -- the calling UI must render text in an editable field and label
everything as AI-suggested, never auto-submit it. See citizen_report.py.
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

# .env lives at the ThirdWave project root, not inside streamlit_app/
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
- If flooding is visible and there are reference objects of known approximate size (cars, doorways, people, \
etc.), estimate water depth in meters using their geometry, and identify 1-3 of those reference objects with \
a PIXEL bounding box [x_min, y_min, x_max, y_max] for the exact image dimensions given to you, plus the \
approximate waterline y-coordinate in pixels near each one. If you can't confidently do this (no clear \
reference object, or no flooding), leave reference_objects empty and depth_estimate_m null -- do not guess.

Respond with ONLY a JSON object, no other text, in this exact shape:
{"shows_flooding": true or false, "description": "...", "suggested_hazard_type": "flash_flood" | "urban_flood" | "river_flood" | null, "note": "brief note on confidence or what's unclear, if anything", "depth_estimate_m": {"low": 0.0, "high": 0.0} or null, "reference_objects": [{"label": "...", "box_px": [x1, y1, x2, y2], "waterline_y_px": 0}]}"""


class VLMError(Exception):
    pass


def _normalize_orientation(image_bytes: bytes) -> bytes:
    """Bakes in EXIF orientation (common on phone camera photos) so the raw
    pixel grid matches how the photo actually displays. Without this, a
    portrait photo stored with a rotation tag still has landscape raw
    dimensions -- the model reasons about the image as it's meant to be
    viewed and returns box_px/waterline_y_px for THAT orientation, but PIL's
    default Image.open ignores the tag, so annotate_image would draw those
    coordinates onto the wrong (unrotated) pixel grid, producing exactly
    the "boxes appear shifted/higher" symptom this fixes. Re-encoding here
    means describe_flood_photo, annotate_image, and the API all agree on
    one orientation regardless of the source photo's EXIF tag."""
    im = Image.open(io.BytesIO(image_bytes))
    im = ImageOps.exif_transpose(im)  # no-op if there's no orientation tag
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
    # This key is identity-linked (tied to an account with multiple
    # workspaces) -- without the workspace header, the API 400s asking
    # which workspace to act in. Confirmed against a real API call.
    headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
    return anthropic.Anthropic(api_key=api_key, default_headers=headers)


def describe_flood_photo(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """Calls the real Anthropic Messages API with the photo. Returns a dict
    matching SYSTEM_PROMPT's JSON shape (description, hazard type, and --
    when the model is confident -- a depth estimate with reference-object
    bounding boxes for annotate_image() to draw). Raises VLMError on any
    failure -- caller must handle this and fall back to manual entry,
    never block submission on this failing."""
    client = _get_client()

    image_bytes = _normalize_orientation(image_bytes)
    media_type = "image/jpeg"
    width, height = Image.open(io.BytesIO(image_bytes)).size
    b64_image = base64.b64encode(image_bytes).decode("ascii")

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
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

    # Sanity-check reference object boxes before trusting them for drawing --
    # same "verify before trust" discipline as everywhere else in this
    # project. Drop anything malformed rather than draw a wrong box.
    valid_objects = []
    for obj in result.get("reference_objects") or []:
        box = obj.get("box_px")
        if (isinstance(box, list) and len(box) == 4
                and 0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
            valid_objects.append(obj)
    result["reference_objects"] = valid_objects

    return result


def annotate_image(image_bytes: bytes, vlm_result: dict) -> bytes | None:
    """Draws the VLM's reference-object boxes + waterline on the photo, if
    any passed the sanity check in describe_flood_photo(). Returns None
    (not a placeholder image) when there's nothing trustworthy to draw --
    caller should fall back to showing the plain photo, not a fake
    annotation."""
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

    for obj in objects:
        box = obj["box_px"]
        draw.rectangle(box, outline=(255, 60, 60), width=line_w)
        label = obj.get("label", "")
        if label:
            ty = max(0, box[1] - font_size - line_w)
            tbox = draw.textbbox((box[0], ty), label, font=font)
            draw.rectangle((tbox[0] - 4, tbox[1] - 2, tbox[2] + 4, tbox[3] + 2), fill=(255, 60, 60))
            draw.text((box[0], ty), label, fill=(255, 255, 255), font=font)
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
