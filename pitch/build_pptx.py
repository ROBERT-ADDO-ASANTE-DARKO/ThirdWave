"""
Build a real, editable .pptx mirroring the ThirdWave Field Report artifact,
so the team can present/edit it without a browser.
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
import os

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "assets")

INK = RGBColor(0x0B, 0x25, 0x45)
INK_SOFT = RGBColor(0x48, 0x60, 0x6B)
INK_FAINT = RGBColor(0x7C, 0x8F, 0x94)
ACCENT = RGBColor(0x1B, 0x7A, 0x9E)
BG = RGBColor(0xEE, 0xF1, 0xEC)
PANEL = RGBColor(0xFF, 0xFF, 0xFF)
PANEL2 = RGBColor(0xF5, 0xF7, 0xF3)
LINE = RGBColor(0xC9, 0xD3, 0xCC)
LOW = RGBColor(0x1E, 0x8A, 0x4C)
MOD = RGBColor(0xB8, 0x86, 0x0B)
VHIGH = RGBColor(0xB0, 0x24, 0x1D)

DISPLAY_FONT = "Georgia"
BODY_FONT = "Calibri"
MONO_FONT = "Consolas"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
SW, SH = prs.slide_width, prs.slide_height
blank = prs.slide_layouts[6]


def add_slide():
    s = prs.slides.add_slide(blank)
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SW, SH)
    bg.fill.solid()
    bg.fill.fore_color.rgb = BG
    bg.line.fill.background()
    bg.shadow.inherit = False
    s.shapes._spTree.remove(bg._element)
    s.shapes._spTree.insert(2, bg._element)
    return s


def add_rule(s, x, y, w, color=LINE, weight=0.75):
    ln = s.shapes.add_connector(1, x, y, x + w, y)
    ln.line.color.rgb = color
    ln.line.width = Pt(weight)
    return ln


def add_text(s, x, y, w, h, text, size=14, color=INK, bold=False, font=BODY_FONT,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=1.15, italic=False,
             letter_spacing=None):
    tb = s.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = 0; tf.margin_right = 0; tf.margin_top = 0; tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = spacing
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.color.rgb = color
    r.font.bold = bold
    r.font.italic = italic
    r.font.name = font
    return tb


def eyebrow(s, x, y, left_text, right_text, w=None):
    w = w or (SW - 2 * x)
    add_rule(s, x, y + Inches(0.32), w, LINE, 1)
    add_text(s, x, y, w / 2, Inches(0.3), left_text, size=10.5, color=INK_FAINT,
              font=MONO_FONT, bold=False)
    add_text(s, x + w / 2, y, w / 2, Inches(0.3), right_text, size=10.5, color=INK_FAINT,
              font=MONO_FONT, align=PP_ALIGN.RIGHT)


def section_head(s, x, y, num, title, w=Inches(10), size=27, box_h=Inches(1.3)):
    add_text(s, x, y, w, box_h, title, size=size, color=INK, bold=False,
              font=DISPLAY_FONT, spacing=1.05)
    add_text(s, SW - Inches(2.3), y + Inches(0.05), Inches(1.8), Inches(0.3), num,
              size=11, color=ACCENT, font=MONO_FONT, align=PP_ALIGN.RIGHT)


def picture_bordered(s, path, x, y, w, h):
    pic = s.shapes.add_picture(path, x, y, width=w, height=h)
    pic.line.color.rgb = LINE
    pic.line.width = Pt(1)
    return pic


MARGIN = Inches(0.55)

# ---------------------------------------------------------------- Slide 1: Cover
s = add_slide()
add_text(s, MARGIN, Inches(0.4), Inches(7), Inches(0.3), "THIRDWAVE — FLOOD EARLY-WARNING SYSTEM",
          size=10.5, color=INK_FAINT, font=MONO_FONT)
add_text(s, SW - Inches(4), Inches(0.4), Inches(3.45), Inches(0.3), "MVP FIELD REPORT · 2026",
          size=10.5, color=INK_FAINT, font=MONO_FONT, align=PP_ALIGN.RIGHT)
add_rule(s, MARGIN, Inches(0.75), SW - 2 * MARGIN)

add_text(s, MARGIN, Inches(1.05), Inches(8), Inches(0.3),
          "05°33'N  00°13'W      ACCRA, GHANA      PILOT DISTRICT · 6 ASSEMBLIES",
          size=10.5, color=INK_FAINT, font=MONO_FONT)

add_text(s, MARGIN, Inches(1.65), Inches(10.5), Inches(2.0),
          "Reading a flooding city with no gauges.",
          size=44, color=INK, font=DISPLAY_FONT, spacing=1.0)

add_text(s, MARGIN, Inches(3.55), Inches(9.2), Inches(1.5),
          "ThirdWave turns free satellite data into an explainable flood-vulnerability picture for "
          "Accra, and puts it in front of the two people who need it most during a storm — the "
          "government officer deciding where to send a pump crew, and the resident deciding whether "
          "to leave.",
          size=16, color=INK_SOFT, font=BODY_FONT, spacing=1.3)

add_rule(s, MARGIN, Inches(5.35), SW - 2 * MARGIN)
metas = [
    ("COMPOSITE SCORE", "SAR + DEM + land cover"),
    ("PILOT COVERAGE", "319 scored zones, 500m grid"),
    ("INTERFACES", "Government console · Citizen app"),
    ("GROUND TRUTH", "Zero local sensors"),
]
mw = (SW - 2 * MARGIN) / 4
for i, (k, v) in enumerate(metas):
    mx = MARGIN + i * mw
    add_text(s, mx, Inches(5.55), mw - Inches(0.2), Inches(0.3), k, size=9.5, color=ACCENT, font=MONO_FONT)
    add_text(s, mx, Inches(5.85), mw - Inches(0.2), Inches(0.6), v, size=13, color=INK, bold=True, font=BODY_FONT)

# ---------------------------------------------------------------- Slide 2: Problem
s = add_slide()
eyebrow(s, MARGIN, Inches(0.45), "01 — THE PROBLEM", "DATA-POOR, STORM-PRONE")
section_head(s, MARGIN, Inches(0.95), "§1",
             "Accra floods every rainy season. It has almost nothing to see it coming with.")
add_text(s, MARGIN, Inches(2.15), Inches(9.5), Inches(1.4),
          "No dense rain-gauge network. No calibrated hydraulic model of the drainage system — "
          "because the drainage system itself is largely undocumented. No shared picture between "
          "the officials who'd respond and the residents in the water's path. Kwame Nkrumah Circle "
          "floods on a predictable basis, and until this project scored it, that pattern lived in "
          "institutional memory and news archives, not in any system a duty officer could query.",
          size=14.5, color=INK_SOFT, spacing=1.35)

stats = [
    ("0", "River or rain gauges instrumenting the pilot district"),
    ("0", "Documented drain/culvert capacity records available"),
    ("3", "Free global data sources this project fuses instead"),
    ("2", "Audiences with no shared system today — govt & citizens"),
]
sw_ = (SW - 2 * MARGIN - Inches(0.03) * 3) / 4
sy = Inches(4.1)
for i, (num, lab) in enumerate(stats):
    sx = MARGIN + i * (sw_ + Inches(0.03))
    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, sx, sy, sw_, Inches(2.0))
    box.fill.solid(); box.fill.fore_color.rgb = PANEL
    box.line.color.rgb = LINE; box.line.width = Pt(0.75)
    box.shadow.inherit = False
    add_text(s, sx + Inches(0.2), sy + Inches(0.2), sw_ - Inches(0.4), Inches(0.7), num,
              size=32, color=INK, bold=True, font=MONO_FONT)
    add_text(s, sx + Inches(0.2), sy + Inches(0.95), sw_ - Inches(0.4), Inches(1.0), lab,
              size=11.5, color=INK_SOFT, spacing=1.25)

# ---------------------------------------------------------------- Slide 3: Data fusion (plates)
s = add_slide()
eyebrow(s, MARGIN, Inches(0.45), "02 — DATA FUSION", "FREE, GLOBAL, REAL")
section_head(s, MARGIN, Inches(0.95), "§2",
             "Three public satellite layers, fused into one explainable score.")
add_text(s, MARGIN, Inches(1.9), Inches(11.5), Inches(0.9),
          "Every plate below is real output from this project's pipeline, over the actual pilot "
          "district. Sentinel-1 radar sees standing water through cloud cover; Copernicus DEM gives "
          "terrain; ESA WorldCover gives surface type. No signup, no cost.",
          size=13, color=INK_SOFT, spacing=1.3)

plates = [
    ("plate_sar.png", "PLATE 2.1", "SAR water occurrence",
     "Sentinel-1, 2020-2024, 40-scene sample. Darker = more frequently water-like."),
    ("plate_dem.png", "PLATE 2.2", "Elevation",
     "Copernicus DEM 30m. Green = low-lying, brown = higher ground."),
    ("plate_worldcover.png", "PLATE 2.3", "Land cover",
     "ESA WorldCover 2021. Red = built-up, blue = water."),
]
pw = Inches(3.75)
ph = Inches(2.65)
gap = Inches(0.25)
px0 = MARGIN
py = Inches(2.75)
for i, (fname, tag, title, sub) in enumerate(plates):
    px = px0 + i * (pw + gap)
    picture_bordered(s, os.path.join(A, fname), px, py, pw, ph)
    add_text(s, px, py + ph + Inches(0.1), pw, Inches(0.3), title, size=13, color=INK, bold=True)
    add_text(s, px, py + ph + Inches(0.4), pw, Inches(0.65), sub, size=10, color=INK_FAINT, spacing=1.2)

fx, fy, fw, fh = MARGIN, Inches(6.75), SW - 2 * MARGIN, Inches(0.6)
fbox = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, fx, fy, fw, fh)
fbox.fill.solid(); fbox.fill.fore_color.rgb = PANEL
fbox.line.color.rgb = LINE; fbox.line.width = Pt(0.75)
fbox.shadow.inherit = False
add_text(s, fx + Inches(0.2), fy + Inches(0.12), fw - Inches(0.4), Inches(0.4),
          "SCORE = 0.45 · SAR_OCC + 0.35 · LOW_ELEV + 0.20 · IMPERVIOUS",
          size=14, color=INK, font=MONO_FONT, anchor=MSO_ANCHOR.MIDDLE)

# ---------------------------------------------------------------- Slide 4: Architecture
s = add_slide()
eyebrow(s, MARGIN, Inches(0.45), "03 — ARCHITECTURE", "PIPELINE & CONSUMERS")
section_head(s, MARGIN, Inches(0.95), "§3", "One computed layer, two very different front doors.")
add_text(s, MARGIN, Inches(1.9), Inches(11.5), Inches(0.6),
          "Heavy geospatial fetches and simulation run offline; the interfaces read small, fast, "
          "precomputed results.",
          size=13, color=INK_SOFT, spacing=1.3)
dw = Inches(11.5); dh = dw * (350 / 864)
picture_bordered(s, os.path.join(A, "diagram_plate.png"), MARGIN, Inches(2.7), dw, dh)

# ---------------------------------------------------------------- Slide 5: What's built (screens)
s = add_slide()
eyebrow(s, MARGIN, Inches(0.4), "04 — WHAT'S BUILT", "WORKING, NOT MOCKED")
section_head(s, MARGIN, Inches(0.8), "§4", "Four interfaces, all screenshotted from the running app.",
             size=25, box_h=Inches(0.95))

feats = [
    ("01_dashboard.png", "District Vulnerability Dashboard",
     "Composite score per assembly, with a toggle onto raw SAR/DEM/WorldCover evidence."),
    ("04_pluvial_circle.png", "Pluvial Flood Simulator",
     "Rainfall-driven ponding proxy over real terrain — Circle: 52cm at 60mm."),
    ("05_flood3d.png", "3D Flood View",
     "Real OSM buildings and roads, true-scale simulated water."),
    ("07_ai_assistant_chat.png", "AI Assistant",
     "Claude with tool-calling over the real computed data."),
]
fw = Inches(5.65); fh_ = Inches(1.85)
gx = Inches(0.15)
x0, y0 = MARGIN, Inches(1.85)
for i, (fname, title, sub) in enumerate(feats):
    col = i % 2; row = i // 2
    fx = x0 + col * (fw + gx)
    fy = y0 + row * (fh_ + Inches(0.8))
    picture_bordered(s, os.path.join(A, fname), fx, fy, fw, fh_)
    add_text(s, fx, fy + fh_ + Inches(0.08), fw, Inches(0.3), title, size=12.5, color=INK, bold=True)
    add_text(s, fx, fy + fh_ + Inches(0.38), fw, Inches(0.4), sub, size=10, color=INK_FAINT, spacing=1.2)

# ---------------------------------------------------------------- Slide 6: VLM in action
s = add_slide()
eyebrow(s, MARGIN, Inches(0.4), "04.1 — CROWDSOURCED REPORTING", "THE VLM IN ACTION")
section_head(s, MARGIN, Inches(0.85), "§4.1",
             "A resident's photo becomes a structured, reviewable report.")
add_text(s, MARGIN, Inches(1.75), Inches(11.5), Inches(0.7),
          "A vision-language model finds a reference object, draws the waterline against it, and "
          "drafts a triage-quality depth estimate — before the resident reviews and edits it. Live "
          "output from the running app.",
          size=13, color=INK_SOFT, spacing=1.3)
vh = Inches(4.5); vw = vh * (1040 / 885)
vx = (SW - vw) / 2
picture_bordered(s, os.path.join(A, "vlm_plate.png"), vx, Inches(2.55), vw, vh)
add_text(s, MARGIN, Inches(2.55) + vh + Inches(0.1), Inches(11), Inches(0.35),
          "Demo photo for this pitch (not a real pilot-district submission): flooded street, Lagos, "
          "2013 — Elgabarty2002, CC BY-SA 4.0, via Wikimedia Commons.",
          size=9.5, color=INK_FAINT, italic=True)

# ---------------------------------------------------------------- Slide 7: AI problems solved
s = add_slide()
eyebrow(s, MARGIN, Inches(0.4), "05 — WHERE AI DOES THE WORK", "FIVE SPECIFIC JOBS")
section_head(s, MARGIN, Inches(0.8), "§5",
             'Not "AI everywhere." AI where the constraint actually required it.',
             size=24, box_h=Inches(1.0))

problems = [
    ("01", "Risk assessment with zero local ground truth",
     "Global ML-classified products fused into one score, fine enough to catch the 2015 Circle disaster a coarser score missed."),
    ("02", "Noisy radar hiding small water bodies",
     "A deep despeckling model (SAR2SAR) cleans Sentinel-1 speckle before water-occurrence is computed."),
    ("03", "Unstructured citizen photos",
     "A vision-language model turns a submitted photo into a structured depth/severity read, resident-validated."),
    ("04", "Hydraulic modeling needing data nobody has",
     "A lightweight cellular-automaton proxy over real terrain — disclosed as a proxy, not a calibrated model."),
    ("05", "GIS tools locking out non-technical officials",
     "Tool-calling chat grounded in the real computed data — plain language in, real answers out."),
]
py0 = Inches(1.95)
row_h = Inches(0.78)
for i, (n, title, desc) in enumerate(problems):
    ry = py0 + i * row_h
    add_rule(s, MARGIN, ry, SW - 2 * MARGIN, LINE, 0.75)
    add_text(s, MARGIN, ry + Inches(0.12), Inches(0.5), Inches(0.4), n, size=12, color=ACCENT, font=MONO_FONT)
    add_text(s, MARGIN + Inches(0.6), ry + Inches(0.08), Inches(4.3), Inches(0.7), title,
              size=13, color=INK, bold=True, spacing=1.15)
    add_text(s, MARGIN + Inches(5.1), ry + Inches(0.08), Inches(6.7), Inches(0.75), desc,
              size=11, color=INK_SOFT, spacing=1.25)
add_rule(s, MARGIN, py0 + 5 * row_h, SW - 2 * MARGIN, LINE, 0.75)

cy = py0 + 5 * row_h + Inches(0.15)
cbox = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, MARGIN, cy, SW - 2 * MARGIN, Inches(1.15))
cbox.fill.solid(); cbox.fill.fore_color.rgb = RGBColor(0xDC, 0xEB, 0xF0)
cbox.line.color.rgb = ACCENT; cbox.line.width = Pt(1.25)
cbox.shadow.inherit = False
add_text(s, MARGIN + Inches(0.3), cy + Inches(0.1), SW - 2 * MARGIN - Inches(0.6), Inches(0.95),
          "The core risk score is a transparent formula, not a trained model. We checked whether a "
          "public satellite flood-extent dataset could justify a predictive model instead — it "
          "couldn't (wrong resolution, not enough local labeled events). Knowing where not to force "
          "AI is the same engineering discipline as knowing where to use it.",
          size=12.5, color=INK, italic=True, spacing=1.3)

# ---------------------------------------------------------------- Slide 8: Roadmap
s = add_slide()
eyebrow(s, MARGIN, Inches(0.45), "06 — ROADMAP", "HONEST NEXT STEPS")
section_head(s, MARGIN, Inches(0.95), "§6", "What's next, gated on what would actually make it better.")

road = [
    ("SHIPPED", LOW, "Composite risk score, 4 government tools, 5 citizen tools, AI assistant",
     "All screenshotted from the running pilot-district app in this report."),
    ("ACCUMULATING NOW", MOD, "Citizen reports as a real ground-truth stream",
     "Each geotagged report with a VLM depth estimate is a sparse, real observation — the kind of anchor data a physics-informed model needs."),
    ("FUTURE DIRECTION", INK_FAINT, "Physics-informed neural network (PINN) for surface flow",
     "Once citizen reports accumulate enough to anchor it, a shallow-water-equation PINN could replace the CA proxy — still bounded by the same missing drainage-capacity data as any hydraulic model."),
]
ry0 = Inches(2.15)
rh = Inches(1.55)
for i, (stage, color, title, desc) in enumerate(road):
    ry = ry0 + i * rh
    add_rule(s, MARGIN, ry, SW - 2 * MARGIN, LINE, 0.75)
    add_text(s, MARGIN, ry + Inches(0.18), Inches(2.3), Inches(0.4), stage, size=11, color=color,
              bold=True, font=MONO_FONT)
    add_text(s, MARGIN + Inches(2.5), ry + Inches(0.14), Inches(9.3), Inches(0.4), title,
              size=14.5, color=INK, bold=True)
    add_text(s, MARGIN + Inches(2.5), ry + Inches(0.55), Inches(9.3), Inches(0.85), desc,
              size=11.5, color=INK_SOFT, spacing=1.3)
add_rule(s, MARGIN, ry0 + 3 * rh, SW - 2 * MARGIN, LINE, 0.75)

# ---------------------------------------------------------------- Slide 9: Close
s = add_slide()
eyebrow(s, MARGIN, Inches(0.5), "07 — CLOSE", "THIRDWAVE")
add_text(s, MARGIN, Inches(1.1), Inches(10.5), Inches(1.7),
          "Built for the officer deciding where to send a pump crew, and the resident deciding "
          "whether to leave.",
          size=30, color=INK, font=DISPLAY_FONT, spacing=1.05)

asks = [
    ("WHAT IT IS", "A working MVP: real satellite fusion, real government & citizen tools, tested end-to-end."),
    ("WHAT IT ISN'T", "Not a calibrated hydraulic model, not a substitute for real sensors — every tool discloses its own limits in-app."),
    ("ASK", "Feedback on the pilot scope, and a path to real citizen-report volume to anchor what comes next."),
]
aw = (SW - 2 * MARGIN - Inches(0.03) * 2) / 3
ay = Inches(3.3)
for i, (k, v) in enumerate(asks):
    ax = MARGIN + i * (aw + Inches(0.03))
    box = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, ax, ay, aw, Inches(2.3))
    box.fill.solid(); box.fill.fore_color.rgb = PANEL
    box.line.color.rgb = LINE; box.line.width = Pt(0.75)
    box.shadow.inherit = False
    add_text(s, ax + Inches(0.22), ay + Inches(0.2), aw - Inches(0.44), Inches(0.3), k,
              size=10.5, color=ACCENT, font=MONO_FONT, bold=True)
    add_text(s, ax + Inches(0.22), ay + Inches(0.6), aw - Inches(0.44), Inches(1.6), v,
              size=12.5, color=INK_SOFT, spacing=1.3)

add_text(s, MARGIN, Inches(6.6), Inches(11.5), Inches(0.4),
          "THIRDWAVE — ACCRA, GHANA · PLATES 2.1-2.3 DERIVED FROM SENTINEL-1 / COPERNICUS DEM / ESA WORLDCOVER",
          size=9, color=INK_FAINT, font=MONO_FONT)

out_path = os.path.join(HERE, "ThirdWave_Field_Report.pptx")
prs.save(out_path)
print("saved", out_path, os.path.getsize(out_path))
