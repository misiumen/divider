"""Geometry for the Arkham divider STLs.

Pipeline per divider:  SVG / font outlines -> `fill()` (the sanitizer: nodes every
self-intersection and keeps faces by SVG fill rule) -> `printable()` (embolden,
drop sub-nozzle features) -> `extrude()` (valid CadQuery prisms) -> union with plate.

Print orientation: flat on the bed, relief (text, icon) facing up.
Colour swap at Z = plate.thickness (1.0 mm = 5 layers @ 0.2); relief = 0.6 mm = 3 layers.
"""
from __future__ import annotations

import functools
import math
import xml.etree.ElementTree as ET

import cadquery as cq
import numpy as np
from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTFont
from shapely import affinity
from shapely.geometry import LineString, Polygon, box
from shapely.ops import polygonize, unary_union

# ------------------------------------------------------------------ sanitizer


def _bezier(p, n=8):
    t = np.linspace(0, 1, n + 1)[1:, None]
    if len(p) == 3:
        return (1 - t) ** 2 * p[0] + 2 * (1 - t) * t * p[1] + t**2 * p[2]
    return (1 - t) ** 3 * p[0] + 3 * (1 - t) ** 2 * t * p[1] + 3 * (1 - t) * t**2 * p[2] + t**3 * p[3]


def pen_contours(ops):
    """fontTools RecordingPen ops -> list of closed contours (Nx2 arrays), curves flattened."""
    out, cur = [], []

    def flush():
        if len(cur) > 2:
            out.append(np.array(cur))

    for op, args in ops:
        pts = [None if a is None else np.asarray(a, float) for a in args]
        if op == "moveTo":
            flush()
            cur = [pts[0]]
        elif op == "lineTo":
            cur.append(pts[0])
        elif op == "curveTo":
            cur.extend(_bezier([cur[-1], *pts]))
        elif op == "qCurveTo":
            off, end = pts[:-1], pts[-1]
            if end is None:  # TrueType contour made of off-curve points only
                end = (off[-1] + off[0]) / 2
                flush()
                cur = [end]
            for i, c in enumerate(off):
                e = end if i == len(off) - 1 else (c + off[i + 1]) / 2
                cur.extend(_bezier([cur[-1], c, e]))
        elif op in ("closePath", "endPath"):
            flush()
            cur = []
    flush()
    return out


def _winding(x, y, ring):
    a, b = ring, np.roll(ring, -1, axis=0)
    cross = (b[:, 0] - a[:, 0]) * (y - a[:, 1]) - (x - a[:, 0]) * (b[:, 1] - a[:, 1])
    up = (a[:, 1] <= y) & (b[:, 1] > y) & (cross > 0)
    down = (a[:, 1] > y) & (b[:, 1] <= y) & (cross < 0)
    return int(up.sum()) - int(down.sum())


def fill(rings, rule="nonzero"):
    """Apply an SVG fill rule to raw contours -> valid (Multi)Polygon.

    Self-intersections, overlaps and unclosed paths are resolved by noding all
    contours into a planar graph and keeping each face whose winding number
    passes the rule. This is what the icon font / slicer would do, done once, cleanly.
    """
    rings = [r for r in rings if len(r) > 2]
    if not rings:
        return Polygon()
    lines = unary_union([LineString(np.vstack([r, r[:1]])) for r in rings])
    keep = []
    for face in polygonize(lines):
        p = face.representative_point()
        w = sum(_winding(p.x, p.y, r) for r in rings)
        if (w != 0) if rule == "nonzero" else (w % 2 == 1):
            keep.append(face)
    return unary_union(keep)


def printable(g, embolden=0.0, min_feature=0.0, tol=0.01):
    """Thicken strokes, remove solid details and gaps thinner than min_feature, decimate vertices."""
    if embolden:
        g = g.buffer(embolden, join_style="round")
    if min_feature:  # opening (thin solid) then closing (thin gaps, speck holes); both break meshing
        r = min_feature / 2
        g = g.buffer(-r, join_style="mitre").buffer(2 * r, join_style="mitre").buffer(-r, join_style="mitre")
    return g.simplify(tol, preserve_topology=True)


def place(g, x, y, align="center"):
    """Move g so its anchor (bbox left/centre/right, vertical centre) sits at (x, y)."""
    minx, miny, maxx, maxy = g.bounds
    ax = {"left": minx, "center": (minx + maxx) / 2, "right": maxx}[align]
    return affinity.translate(g, x - ax, y - (miny + maxy) / 2)


# ------------------------------------------------------------------ sources


@functools.lru_cache(maxsize=None)
def font(path):
    return Font(path)


class Font:
    def __init__(self, path):
        self.path = path
        self.ttf = TTFont(path)
        self.glyphs = self.ttf.getGlyphSet()
        self.cmap = self.ttf.getBestCmap()
        self.upm = self.ttf["head"].unitsPerEm

    def _glyph(self, ch):
        name = self.cmap.get(ord(ch))
        if name is None:
            raise KeyError(f"{self.path} has no glyph for {ch!r}")
        return self.glyphs[name]

    def width(self, text, size):
        return sum(self._glyph(c).width for c in text) * size / self.upm

    def rings(self, text, size, x=0.0, y=0.0):
        s, out = size / self.upm, []
        for ch in text:
            g = self._glyph(ch)
            pen = RecordingPen()
            g.draw(pen)
            out += [r * s + (x, y) for r in pen_contours(pen.value)]
            x += g.width * s
        return out


def _wrap(f, text, size, max_width):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and f.width(trial, size) > max_width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur]


def text_geom(path, text, size, max_width=None, max_lines=1, line_spacing=1.2, min_size=3.0, align="center"):
    """Text block as a clean (Multi)Polygon, origin at the first baseline.

    Words wrap into at most max_lines lines; the size shrinks (down to min_size)
    until the block fits max_width. Returns (geometry, size used).
    """
    f = font(path)
    while True:
        lines = _wrap(f, text, size, max_width) if max_width else [text]
        too_wide = max_width and max(f.width(l, size) for l in lines) > max_width
        if (len(lines) <= max_lines and not too_wide) or size <= min_size:
            break
        size *= 0.95
    block = max(f.width(l, size) for l in lines)
    rings = []
    for i, line in enumerate(lines):
        w = f.width(line, size)
        x = {"left": 0.0, "center": (block - w) / 2, "right": block - w}[align]
        rings += f.rings(line, size, x, -i * size * line_spacing)
    return fill(rings), size


def svg_geom(path, size, rule="nonzero"):
    """SVG file (path elements only) -> clean (Multi)Polygon, viewBox height scaled to `size` mm."""
    root = ET.parse(path).getroot()
    vb = [float(v) for v in root.get("viewBox", "0 0 1024 1024").split()]
    pen = RecordingPen()
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] == "path" and el.get("d"):
            parse_path(el.get("d"), pen)
    s = size / vb[3]
    return fill([r * (s, -s) for r in pen_contours(pen.value)], rule)  # SVG is y-down


# ------------------------------------------------------------------ 2D -> CadQuery


def _polys(g):
    return [p for p in getattr(g, "geoms", [g]) if isinstance(p, Polygon) and not p.is_empty]


def extrude(g, z0, h):
    """(Multi)Polygon -> Workplane holding one valid prism per polygon, z0 .. z0+h."""
    solids = []
    for p in _polys(g):
        def wire(coords):
            return cq.Wire.makePolygon([cq.Vector(x, y, z0) for x, y in coords[:-1]], close=True)

        face = cq.Face.makeFromWires(wire(p.exterior.coords), [wire(i.coords) for i in p.interiors])
        solid = cq.Solid.extrudeLinear(face, cq.Vector(0, 0, h))
        if not solid.isValid():
            raise ValueError("prism is not a valid solid; polygon survived the sanitizer with a defect")
        solids.append(solid)
    return cq.Workplane("XY").newObject(solids)


# ------------------------------------------------------------------ divider


def tab_x(L, slot):
    """Centre x of the tab for a stagger slot (0 = leftmost)."""
    P, T = L["plate"], L["tab"]
    span = P["width"] - 2 * T["margin"] - T["width"]
    step = span / (T["slots"] - 1) if T["slots"] > 1 else 0
    return -P["width"] / 2 + T["margin"] + T["width"] / 2 + (slot * step if T["slots"] > 1 else span / 2)


def plate(L, slot):
    """Body + tab outline with every corner rounded, filleted top edge, chamfered bottom edge."""
    P, T = L["plate"], L["tab"]
    W, H, r = P["width"], P["height"], P["corner_radius"]
    if T["margin"] <= 2 * r or T["height"] <= 2 * r:  # exactly 2r fails inside OCC's 2D fillet
        raise ValueError("tab.margin and tab.height must exceed 2 * plate.corner_radius (two fillets share each short edge)")
    tx, hw, top = tab_x(L, slot), T["width"] / 2, H / 2 + T["height"]
    pts = [(-W / 2, -H / 2), (W / 2, -H / 2), (W / 2, H / 2), (tx + hw, H / 2), (tx + hw, top), (tx - hw, top), (tx - hw, H / 2), (-W / 2, H / 2)]
    sketch = cq.Sketch().polygon(pts).vertices().fillet(r)
    return (
        cq.Workplane("XY")
        .placeSketch(sketch)
        .extrude(P["thickness"])
        .edges(">Z")
        .fillet(P["top_fillet"])
        .edges("<Z")
        .chamfer(P["bottom_chamfer"])
    )


def pattern(L, keepout):
    """Holes (MultiPolygon) for the body: hex or grid cells inside the border, away from the relief."""
    R, P = L["pattern"], L["plate"]
    kind = R["type"]
    if kind == "solid":
        return None
    W, H, cell, pitch = P["width"], P["height"], R["cell"], R["cell"] + R["wall"]
    region = box(-W / 2, -H / 2, W / 2, H / 2).buffer(-R["border"])
    if kind == "hex":  # pointy-top, flat-to-flat = cell, uniform wall in all 6 directions
        rc = cell / math.sqrt(3)
        shape = Polygon([(rc * math.cos(math.radians(90 + 60 * k)), rc * math.sin(math.radians(90 + 60 * k))) for k in range(6)])
        py, stagger = pitch * math.sqrt(3) / 2, pitch / 2
    elif kind == "grid":
        shape, py, stagger = box(-cell / 2, -cell / 2, cell / 2, cell / 2), pitch, 0
    else:
        raise ValueError(f"pattern.type {kind!r}: use solid, hex or grid")
    rows, cols = int(H / py) + 2, int(W / pitch) + 2
    ko = keepout.buffer(R["keepout_pad"])
    cells = [
        affinity.translate(shape, i * pitch + (stagger if j % 2 else 0), j * py)
        for j in range(-rows, rows + 1)
        for i in range(-cols, cols + 1)
    ]
    return unary_union([c for c in cells if c.within(region) and not c.intersects(ko)])


def build(spec, L, icon_dir):
    """One divider. spec: title, count, icon (name or None), slot. Returns a Workplane with one solid."""
    P, T = L["plate"], L["tab"]
    th, rh = P["thickness"], L["relief"]["height"]

    def origin(cfg):
        if cfg.get("on") == "tab":
            return tab_x(L, spec["slot"]), P["height"] / 2 + T["height"] / 2
        return 0.0, 0.0

    parts = []
    for key, text in (("title", spec["title"]), ("count", str(spec["count"]))):
        c = L[key]
        g, _ = text_geom(c["font"], text, c["size"], c.get("max_width"), c.get("max_lines", 1), c.get("line_spacing", 1.2), c.get("min_size", 3.0), c.get("align", "center"))
        ox, oy = origin(c)
        parts.append(printable(place(g, ox + c["x"], oy + c["y"], c.get("align", "center")), c.get("embolden", 0), c.get("min_feature", 0)))
    c = L["icon"]
    if spec.get("icon"):
        ox, oy = origin(c)
        g = svg_geom(icon_dir / f"{spec['icon']}.svg", c["size"])
        parts.append(printable(place(g, ox + c["x"], oy + c["y"]), c.get("embolden", 0), c.get("min_feature", 0)))
    relief = unary_union(parts)

    base = plate(L, spec["slot"])
    holes = pattern(L, relief)
    if holes is not None and not holes.is_empty:
        base = base.cut(extrude(holes, -1, th + 2))
    result = base.union(extrude(relief, th, rh))
    if len(result.solids().vals()) != 1 or not result.val().isValid():
        raise ValueError("divider did not fuse into one valid solid")
    return result


def export(result, path):
    cq.exporters.export(result, str(path), tolerance=0.01, angularTolerance=0.1)
