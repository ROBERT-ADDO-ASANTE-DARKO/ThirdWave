"""
bgt_draw.py — draw BGT polygons WITH their holes (courtyards, islands).

Drawing `poly.exterior` alone silently paints every courtyard as solid
building -- found when a flooded courtyard appeared to sit "inside a
building" in the Amsterdam surface-flood figure (the solver was right: the
courtyard is not a wall; the plot was wrong). Rings are oriented (exterior
CCW, holes CW) and combined into one compound path so matplotlib cuts the
holes out correctly.
"""
from __future__ import annotations

import numpy as np
from matplotlib.collections import PatchCollection
from matplotlib.patches import PathPatch
from matplotlib.path import Path
from shapely.geometry import shape
from shapely.geometry.polygon import orient

LAYER_COLORS = {"waterdeel": "#dfe9f2", "pand": "#d6d1c7"}


def _patches(feats, bounds=None):
    out = []
    for f in feats:
        try:
            g = shape(f["geometry"])
        except Exception:
            continue
        if g.is_empty:
            continue
        if bounds is not None:
            bx0, by0, bx1, by1 = g.bounds
            x0, x1, y0, y1 = bounds
            if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
                continue
        for poly in getattr(g, "geoms", [g]):
            poly = orient(poly, 1.0)
            verts, codes = [], []
            for ring in [poly.exterior, *poly.interiors]:
                v = np.asarray(ring.coords)
                verts.extend(v)
                codes.extend([Path.MOVETO] + [Path.LINETO] * (len(v) - 2) + [Path.CLOSEPOLY])
            out.append(PathPatch(Path(verts, codes)))
    return out


def draw_bgt(ax, bgt, bounds=None, offset=(0.0, 0.0), layers=("waterdeel", "pand")):
    """bounds = (x0, x1, y0, y1) in RD to skip far-away polygons; offset shifts coords."""
    for layer in layers:
        patches = _patches(bgt[layer], bounds)
        if not patches:
            continue
        pc = PatchCollection(patches, facecolor=LAYER_COLORS[layer], edgecolor="none", zorder=1)
        if offset != (0.0, 0.0):
            from matplotlib.transforms import Affine2D
            pc.set_transform(Affine2D().translate(-offset[0], -offset[1]) + ax.transData)
        ax.add_collection(pc)
