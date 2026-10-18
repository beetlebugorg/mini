#!/usr/bin/env python3
"""Bluespeaker Mini: A3 engineering drawings (SVG and PDF) from the STEP parts.

    uv run cad/mini_report.py --step     # write cad/step-mini/ first
    uv run cad/mini_drawings.py          # docs/drawings-mini/*.svg and docs/Bluespeaker-Mini-Drawings.pdf

The views use the OpenCascade hidden-line removal (the same algorithm as FreeCAD TechDraw).
Sections cut the parts with a plane and hatch the cut faces. All sizes are in millimetres.
"""

import functools
import http.server
import json
import math
import socketserver
import subprocess
import threading
from pathlib import Path

from build123d import Box, GeomType, Plane, Pos, Rectangle, Vector, import_step

ROOT = Path(__file__).resolve().parent.parent
STEP = ROOT / "cad" / "step-mini"
OUT = ROOT / "docs" / "drawings-mini"
REV, DATE = "0.3", "2026-10-11"
META = {x["name"]: x for x in json.loads((STEP / "parts.json").read_text())}


@functools.lru_cache(maxsize=None)
def part(name):
    return import_step(str(STEP / f"{name}.step"))


# ------------------------------------------------------------------ projection

DIRS = {  # name: (viewer direction from the target, up)
    "front": ((0, -1, 0), (0, 0, 1)), "back": ((0, 1, 0), (0, 0, 1)), "top": ((0, 0, 1), (0, 1, 0)),
    "right": ((1, 0, 0), (0, 0, 1)), "left": ((-1, 0, 0), (0, 0, 1)), "bottom": ((0, 0, -1), (0, -1, 0)),
    "iso": ((1, -1.4, 0.9), (0, 0, 1)),
}


class View:
    """One orthographic view on a sheet. look: name in DIRS. at: model point at the view centre.
    page: (x, y) of that point on the sheet, from the bottom left. scale: sheet mm per model mm."""

    def __init__(self, look, at, page, scale):
        d, up = DIRS[look]
        self.F = -Vector(*d).normalized()  # viewing direction
        U = Vector(*up)
        self.R = self.F.cross(U).normalized()
        self.U = self.R.cross(self.F).normalized()
        self.eye = Vector(*d).normalized()
        self.at = Vector(*at)
        self.page = page
        self.s = scale

    def uv(self, p):
        q = Vector(*p) - self.at
        return q.dot(self.R), q.dot(self.U)

    def xy(self, p):
        """Model point to SVG coordinates (mm, y down on an A3 sheet)."""
        u, v = self.uv(p)
        return self.page[0] + u * self.s, 297 - (self.page[1] + v * self.s)

    def xy2(self, u, v):
        return self.page[0] + u * self.s, 297 - (self.page[1] + v * self.s)


def edge_path(e, view, step=0.25):
    if e.geom_type == GeomType.LINE:
        pts = [e.position_at(0), e.position_at(1)]
    else:
        n = max(6, int(e.length * view.s / step))
        pts = [e.position_at(i / n) for i in range(n + 1)]
    # project_to_viewport returns 2D points in the viewport frame (u, v, 0)
    return "M" + " L".join(f"{view.xy2(p.X, p.Y)[0]:.3f},{view.xy2(p.X, p.Y)[1]:.3f}" for p in pts)


def project(shapes, view, hidden=True):
    vis, hid = [], []
    for s in shapes:
        a, b = s.project_to_viewport(view.at + view.eye * 2000, view.U, view.at)
        vis += a
        hid += b
    out = ['<g class="vis">' + "".join(f'<path d="{edge_path(e, view)}"/>' for e in vis) + "</g>"]
    if hidden:
        out.append('<g class="hid">' + "".join(f'<path d="{edge_path(e, view)}"/>' for e in hid) + "</g>")
    return "".join(out)


def cut_keep(shape, origin, normal, window=None):
    """The part of shape behind the plane (on the side away from the viewer). window: (min, max) box to clip to."""
    n = Vector(*normal).normalized()
    big = 2000
    keep = Pos(*(Vector(*origin) - n * (big / 2))) * Box(big, big, big)
    try:
        r = shape & keep
        if window:
            lo, hi = window
            r = r & Pos(*[(a + b) / 2 for a, b in zip(lo, hi)]) * Box(*[b - a for a, b in zip(lo, hi)])
        return r if r is not None and r.volume > 1e-4 else None
    except Exception:
        return None


def section_hatch(shape, view, origin, normal, k):
    """Hatched cut faces of shape in the plane (origin, normal)."""
    n = Vector(*normal)
    pl = Plane(origin=origin, z_dir=n)
    face = pl * Rectangle(1500, 1500)
    try:
        cut = shape & face
    except Exception:
        return ""
    if cut is None:
        return ""
    out = []
    for f in cut.faces():
        d = ""
        for w in [f.outer_wire(), *f.inner_wires()]:
            npts = max(16, int(w.length * view.s / 0.25))
            pts = [w.position_at(i / npts) for i in range(npts)]
            d += "M" + " L".join(f"{view.xy(p)[0]:.3f},{view.xy(p)[1]:.3f}" for p in pts) + " Z "
        out.append(f'<path d="{d}" fill="url(#hatch{k % 4})" fill-rule="evenodd" stroke="#000" stroke-width="0.35"/>')
    return "".join(out)


# ------------------------------------------------------------------ annotation


def arrow(x, y, ang):
    a, L, w = math.radians(ang), 2.6, 0.9
    p1 = (x - L * math.cos(a) + w * math.sin(a), y - L * math.sin(a) - w * math.cos(a))
    p2 = (x - L * math.cos(a) - w * math.sin(a), y - L * math.sin(a) + w * math.cos(a))
    return f'<path d="M{x:.2f},{y:.2f} L{p1[0]:.2f},{p1[1]:.2f} L{p2[0]:.2f},{p2[1]:.2f} Z" class="arr"/>'


def dim(view, p1, p2, axis, off, text=None, prefix=""):
    """Linear dimension. axis 'h' or 'v' on the sheet. off: dimension line offset in sheet mm (+ right or up)."""
    x1, y1 = view.xy(p1)
    x2, y2 = view.xy(p2)
    out = []
    if axis == "h":
        val = abs(view.uv(p2)[0] - view.uv(p1)[0])
        yd = min(y1, y2) - off if off > 0 else max(y1, y2) - off
        out.append(f'<path class="thin" d="M{x1:.2f},{y1:.2f} L{x1:.2f},{yd + (-1.5 if off > 0 else 1.5):.2f} M{x2:.2f},{y2:.2f} L{x2:.2f},{yd + (-1.5 if off > 0 else 1.5):.2f}"/>')
        a, b = sorted((x1, x2))
        inside = b - a > 9
        out.append(f'<path class="thin" d="M{a - (0 if inside else 6):.2f},{yd:.2f} L{b + (0 if inside else 6):.2f},{yd:.2f}"/>')
        out += [arrow(a, yd, 180 if inside else 0), arrow(b, yd, 0 if inside else 180)]
        tx, ty, rot = (a + b) / 2, yd - 1.0, 0
        if not inside:
            tx = b + 8
    else:
        val = abs(view.uv(p2)[1] - view.uv(p1)[1])
        xd = max(x1, x2) + off if off > 0 else min(x1, x2) + off
        out.append(f'<path class="thin" d="M{x1:.2f},{y1:.2f} L{xd + (1.5 if off > 0 else -1.5):.2f},{y1:.2f} M{x2:.2f},{y2:.2f} L{xd + (1.5 if off > 0 else -1.5):.2f},{y2:.2f}"/>')
        a, b = sorted((y1, y2))
        inside = b - a > 9
        out.append(f'<path class="thin" d="M{xd:.2f},{a - (0 if inside else 6):.2f} L{xd:.2f},{b + (0 if inside else 6):.2f}"/>')
        out += [arrow(xd, a, 270 if inside else 90), arrow(xd, b, 90 if inside else 270)]
        tx, ty, rot = xd - 1.0, (a + b) / 2, -90
        if not inside:
            ty = a - 8
    t = text or f"{prefix}{val:.2f}".rstrip("0").rstrip(".")
    out.append(f'<text class="dim" x="{tx:.2f}" y="{ty:.2f}" transform="rotate({rot} {tx:.2f} {ty:.2f})" text-anchor="middle">{t}</text>')
    return "".join(out)


def leader(view, p, text, dx, dy, anchor="start"):
    x, y = view.xy(p)
    tx, ty = x + dx, y - dy
    end = tx - 1 if anchor == "start" else tx + 1
    return (f'<path class="thin" d="M{x:.2f},{y:.2f} L{end:.2f},{ty - 1:.2f}"/>' + f'<circle cx="{x:.2f}" cy="{y:.2f}" r="0.5" class="dot"/>'
            + f'<text class="note" x="{tx:.2f}" y="{ty:.2f}" text-anchor="{anchor}">{text}</text>')


def balloon(view, p, n, dx, dy):
    x, y = view.xy(p)
    bx, by = x + dx, y - dy
    L = math.hypot(bx - x, by - y) or 1
    ex, ey = bx - (bx - x) / L * 3.2, by - (by - y) / L * 3.2
    return (f'<path class="thin" d="M{x:.2f},{y:.2f} L{ex:.2f},{ey:.2f}"/><circle cx="{x:.2f}" cy="{y:.2f}" r="0.55" class="dot"/>'
            f'<circle cx="{bx:.2f}" cy="{by:.2f}" r="3.2" class="bal"/><text class="baln" x="{bx:.2f}" y="{by + 1.2:.2f}" text-anchor="middle">{n}</text>')


def label(x, y, text, size=4.0):
    return f'<text class="lbl" x="{x:.2f}" y="{297 - y:.2f}" text-anchor="middle" style="font-size:{size}px">{text}</text>'


def notes(x, y, lines, size=3.0, width=None):
    out = []
    for i, ln in enumerate(lines):
        out.append(f'<text class="note" x="{x:.2f}" y="{297 - y + i * size * 1.45:.2f}" style="font-size:{size}px">{ln}</text>')
    return "".join(out)


def detail_circle(view, p, r, ref):
    x, y = view.xy(p)
    rr = r * view.s
    return (f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{rr:.2f}" class="thinc"/>'
            f'<text class="lbl" x="{x + rr * 0.75 + 2:.2f}" y="{y - rr * 0.75 - 1:.2f}" style="font-size:4.5px">{ref}</text>')


def cut_line(view, p1, p2, ref):
    x1, y1 = view.xy(p1)
    x2, y2 = view.xy(p2)
    return (f'<path class="cutl" d="M{x1:.2f},{y1:.2f} L{x2:.2f},{y2:.2f}"/>'
            f'<text class="lbl" x="{x1:.2f}" y="{y1 - 2:.2f}" text-anchor="middle" style="font-size:4.5px">{ref}</text>'
            f'<text class="lbl" x="{x2:.2f}" y="{y2 - 2:.2f}" text-anchor="middle" style="font-size:4.5px">{ref}</text>')


# ------------------------------------------------------------------ sheet

CSS = """
.vis path{fill:none;stroke:#000;stroke-width:0.35;stroke-linecap:round;stroke-linejoin:round}
.hid path{fill:none;stroke:#000;stroke-width:0.18;stroke-dasharray:1.2 0.8}
.thin{fill:none;stroke:#000;stroke-width:0.18}
.thinc{fill:none;stroke:#000;stroke-width:0.25;stroke-dasharray:4 1 0.6 1}
.cutl{fill:none;stroke:#000;stroke-width:0.5;stroke-dasharray:6 1.2 1 1.2}
.arr{fill:#000}
.dot{fill:#000}
.bal{fill:#fff;stroke:#000;stroke-width:0.25}
text{font-family:'DejaVu Sans',Inter,Helvetica,sans-serif;fill:#000}
.dim{font-size:2.8px}
.note{font-size:2.8px}
.baln{font-size:3.2px;font-weight:700}
.lbl{font-weight:700}
.tb{font-size:2.4px;fill:#555}
.tbv{font-size:3.6px}
.frame{fill:none;stroke:#000;stroke-width:0.7}
.tbl{fill:none;stroke:#000;stroke-width:0.35}
"""


def hatch_defs():
    out = []
    for i, (ang, sp) in enumerate(((45, 1.4), (-45, 1.4), (45, 0.8), (-45, 0.8))):
        out.append(f'<pattern id="hatch{i}" patternUnits="userSpaceOnUse" width="{sp}" height="{sp}" patternTransform="rotate({ang})">'
                   f'<rect width="{sp}" height="{sp}" fill="#fff"/><line x1="0" y1="0" x2="0" y2="{sp}" stroke="#000" stroke-width="0.13"/></pattern>')
    return "".join(out)


def title_block(n, total, title, sub, scale, material, number):
    x0, y0, w, h = 230, 297 - 10 - 40, 180, 40
    rows = [(x0, y0, w, 14, "Title", title, 6.0), (x0, y0 + 14, w, 8, "Subject", sub, 3.6)]
    cells = [("Drawing no.", number), ("Revision", REV), ("Date", DATE), ("Scale", scale), ("Sheet", f"{n} / {total}")]
    out = [f'<rect class="tbl" x="{x0}" y="{y0}" width="{w}" height="{h}"/>']
    for x, y, ww, hh, k, v, size in rows:
        out.append(f'<rect class="tbl" x="{x}" y="{y}" width="{ww}" height="{hh}"/><text class="tb" x="{x + 1.5}" y="{y + 3}">{k}</text>'
                   f'<text x="{x + 1.5}" y="{y + hh - 2}" style="font-size:{size}px;font-weight:{700 if size > 4 else 400}">{v}</text>')
    cw = w / len(cells)
    for i, (k, v) in enumerate(cells):
        x = x0 + i * cw
        out.append(f'<rect class="tbl" x="{x}" y="{y0 + 22}" width="{cw}" height="9"/><text class="tb" x="{x + 1.5}" y="{y0 + 25}">{k}</text>'
                   f'<text class="tbv" x="{x + 1.5}" y="{y0 + 29.7}">{v}</text>')
    out.append(f'<rect class="tbl" x="{x0}" y="{y0 + 31}" width="{w * 0.62}" height="9"/><text class="tb" x="{x0 + 1.5}" y="{y0 + 34}">Material</text>'
               f'<text class="tbv" x="{x0 + 1.5}" y="{y0 + 38.5}">{material}</text>')
    out.append(f'<rect class="tbl" x="{x0 + w * 0.62}" y="{y0 + 31}" width="{w * 0.38}" height="9"/><text class="tb" x="{x0 + w * 0.62 + 1.5}" y="{y0 + 34}">Tolerance unless shown · units</text>'
               f'<text class="tbv" x="{x0 + w * 0.62 + 1.5}" y="{y0 + 38.5}">±0.2 · mm · third angle</text>')
    # third-angle symbol
    sx, sy = x0 - 22, y0 + 28
    out.append(f'<path class="tbl" d="M{sx},{sy - 4} L{sx + 8},{sy - 2.5} L{sx + 8},{sy + 2.5} L{sx},{sy + 4} Z"/>'
               f'<circle class="tbl" cx="{sx + 15}" cy="{sy}" r="4"/><circle class="tbl" cx="{sx + 15}" cy="{sy}" r="1.8"/>')
    out.append(f'<text class="tb" x="{x0 + w - 1.5}" y="{y0 - 1.5}" text-anchor="end">Bluespeaker Mini · build123d model cad/bluespeaker_mini.py</text>')
    return "".join(out)


SHEETS = []


def sheet(title, sub, scale, material, number, body):
    SHEETS.append(dict(title=title, sub=sub, scale=scale, material=material, number=number, body=body))


def write_sheets():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    files = []
    for i, s in enumerate(SHEETS):
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" viewBox="0 0 420 297">'
               f'<style>{CSS}</style><defs>{hatch_defs()}</defs><rect width="420" height="297" fill="#fff"/>'
               f'<rect class="frame" x="20" y="10" width="390" height="277"/>{s["body"]}'
               f'{title_block(i + 1, len(SHEETS), s["title"], s["sub"], s["scale"], s["material"], s["number"])}</svg>')
        f = OUT / f"{i + 1:02d}-{s['number']}.svg"
        f.write_text(svg)
        files.append(f)
    html = ('<!doctype html><html><head><meta charset="utf-8"><style>@page{size:420mm 297mm;margin:0}body{margin:0}'
            'img{display:block;width:420mm;height:297mm;page-break-after:always}</style></head><body>'
            + "".join(f'<img src="{f.name}">' for f in files) + "</body></html>")
    (OUT / "index.html").write_text(html)
    (OUT / "sheets.json").write_text(json.dumps([{"file": f.name, "number": x["number"], "title": x["title"], "subject": x["sub"],
                                                  "scale": x["scale"]} for f, x in zip(files, SHEETS)], indent=1))
    pdf = ROOT / "docs" / "Bluespeaker-Mini-Drawings.pdf"
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
    http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)  # a free port
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    subprocess.run(["chromium", "--headless=new", "--no-sandbox", "--no-pdf-header-footer", "--virtual-time-budget=15000",
                    f"--print-to-pdf={pdf}", f"http://127.0.0.1:{srv.server_address[1]}/index.html"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    srv.shutdown()
    print("  wrote", len(files), "sheets and", pdf)


# ------------------------------------------------------------------ model values (from MParams)

W, H, D = 166.0, 108.0, 94.0
FY, BFY, BBY, RY = -47.0, -45.5, -41.5, 47.0  # front, baffle front, baffle back, rear
PW, PH = 159.4, 101.4
SX, SZ0, SZ1 = 75.5, 7.5, 100.5  # corner screws
GZ0, GZ1 = 33.5, 104.7  # grille bottom and top
TZ, TX = 13.0, 61.3  # tray screw
SPK = 37.0, 69.5
POT, AUX = (45.0, 18.1), (18.0, 15.1)


def ga():
    names = ["sleeve", "baffle", "grille", "control_strip", "knob", "rear_panel", "screws_front", "screws_rear"]
    shapes = [part(n) for n in names]
    bb = shapes[0].bounding_box()
    c = (bb.center().X, bb.center().Y, bb.center().Z)
    f = View("front", c, (118, 205), 1.0)
    r = View("right", c, (268, 205), 1.0)
    t = View("top", c, (118, 92), 1.0)
    iso = View("iso", c, (362, 205), 0.36)
    b = [project(shapes, f, hidden=False), project(shapes, r, hidden=False), project(shapes, t, hidden=False), project(shapes, iso, hidden=False)]
    b += [dim(f, (-83, FY, 0), (83, FY, 0), "h", -10), dim(f, (-83, FY, 0), (-83, FY, H), "v", -10),
          dim(r, (83, -47, 0), (83, 47, 0), "h", -10), dim(t, (-83, -47, H), (-83, 47, H), "v", -10),
          dim(f, (-SX, FY, SZ1), (SX, FY, SZ1), "h", 12), dim(f, (SX, FY, SZ0), (SX, FY, SZ1), "v", 14),
          label(118, 275, "FRONT"), label(268, 275, "RIGHT"), label(118, 146, "TOP"), label(362, 250, "ISOMETRIC (0.36:1)")]
    b.append(notes(248, 96, ["Grille (grey) and control strip (white) snap onto", "the orange baffle. Four M3 socket head cap screws",
                              "show in the corners, flush with the cover faces.", "Feet, drivers, and the amplifier are not shown."]))
    sheet("Bluespeaker Mini", "General arrangement", "1:1", "PLA (printed parts)", "BSM-00", "".join(b))


def part_sheet(name, number, sub, views, dims_fn, note_lines, material=None, extra=None):
    s = part(name)
    out = []
    vv = {}
    c = s.bounding_box().center()
    for key, (look, _at, page, scale, hidden) in views.items():
        v = View(look, (c.X, c.Y, c.Z), page, scale)
        vv[key] = v
        out.append(project([s], v, hidden))
    bb = s.bounding_box()
    corners = [(x, y, z) for x in (bb.min.X, bb.max.X) for y in (bb.min.Y, bb.max.Y) for z in (bb.min.Z, bb.max.Z)]
    for key, v in vv.items():
        top = max(v.uv(q)[1] for q in corners) * v.s + v.page[1]
        sc = "" if v.s == 1 else f" ({v.s:g}:1)"
        out.append(label(v.page[0], top + 6, key.upper() + sc))
    out += dims_fn(vv)
    if extra:
        out += extra(vv)
    out.append(notes(248, 96, note_lines))
    col = META[name]["process"]
    mat = material or ("PLA, " + col.split(",")[1].strip() if "," in col else "PLA")
    sheet("Bluespeaker Mini", sub, "1:1", mat, number, "".join(out))


def sheets_parts():
    # sleeve
    part_sheet("sleeve", "BSM-01", "Sleeve", {
        "front": ("front", (0, 0, H / 2), (120, 190), 1.0, False), "right": ("right", (0, 0, H / 2), (300, 190), 1.0, True),
        "top": ("top", (0, 0, 0), (120, 75), 1.0, True)},
        lambda v: [dim(v["front"], (-83, FY, 0), (83, FY, 0), "h", -10), dim(v["front"], (-83, FY, 0), (-83, FY, H), "v", -10),
                   dim(v["front"], (-80, FY, 54), (-83, FY, 54), "h", 30, "3"), dim(v["front"], (-SX, FY, SZ1), (SX, FY, SZ1), "h", 10),
                   dim(v["front"], (SX, FY, SZ0), (SX, FY, SZ1), "v", 12), dim(v["right"], (83, -47, 0), (83, 47, 0), "h", -10)],
        ["Print front opening down. Profile: PLA Shell 0.25.", "Supports from the build plate below the four front posts only.",
         "Front posts: pilot Ø1.6, drill Ø4.0 x 7 after the print, insert M3 x 3.", "Rear posts: printed Ø4.0, 0.5 x 45° relief, 45° gussets.",
         "Lead-in chamfer 0.6 x 45° inside the front opening.", "Panel opening 160.0 x 102.0 (panels 159.4 x 101.4)."])
    # baffle
    part_sheet("baffle", "BSM-02", "Front baffle", {
        "front": ("front", (0, 0, H / 2), (120, 190), 1.0, False), "right": ("right", (0, 0, H / 2), (300, 190), 1.0, True),
        "top": ("top", (0, 0, 0), (120, 80), 1.0, True)},
        lambda v: [dim(v["front"], (-PW / 2, FY, 3.3), (PW / 2, FY, 3.3), "h", -10), dim(v["front"], (-PW / 2, FY, 3.3), (-PW / 2, FY, 104.7), "v", -10),
                   dim(v["front"], (-37, FY, SPK[1]), (37, FY, SPK[1]), "h", 40), dim(v["front"], (-SX, FY, SZ1), (SX, FY, SZ1), "h", 15),
                   dim(v["front"], (SX, FY, SZ0), (SX, FY, SZ1), "v", 9), dim(v["front"], (37, FY, 3.3), (37, FY, SPK[1]), "v", 49),
                   dim(v["right"], (80, BFY, 3.3), (80, BBY + 3, 3.3), "h", -10), dim(v["right"], (80, BFY, 3.3), (80, BBY, 3.3), "h", -18),
                   leader(v["front"], (37 + 32.5 * 0.7, FY, SPK[1] + 32.5 * 0.7), "Ø65 cut-out, 2 x 45° flare", 18, 18),
                   leader(v["front"], (POT[0], FY, POT[1]), "Nut recess Ø14 x 1.5, hole Ø7.5", 28, -14),
                   leader(v["front"], (AUX[0], FY, AUX[1]), "AUX counterbore Ø10 x 3, hole Ø6.4", 10, -20),
                   leader(v["front"], (63.75, FY, 101.7), "Snap pocket (8x), see BSM-09", 12, 10)],
        ["Print front face down. Profile: PLA Parts 0.25. No supports.", "Counterbores Ø6.0 x 1.5 (front) and x 2.25 (tray), membrane 0.25:",
         "drill Ø3.4 from the back after the print.", "Cut the pot and AUX membranes with a knife.",
         "Spacer frames 70 x 70, 3 thick, 10 x 45° corners: 8 inserts M3 x 3.", "Snap pockets: 3.0 deep, 45° lip, see BSM-09."])
    # grille
    part_sheet("grille", "BSM-03", "Front grille (lattice)", {
        "front": ("front", (0, 0, 69.1), (120, 200), 1.0, False), "back": ("back", (0, 0, 69.1), (120, 110), 1.0, False),
        "right": ("right", (0, 0, 69.1), (300, 200), 1.0, True)},
        lambda v: [dim(v["front"], (-PW / 2, FY, GZ0), (PW / 2, FY, GZ0), "h", -8), dim(v["front"], (-PW / 2, FY, GZ0), (-PW / 2, FY, GZ1), "v", -10),
                   dim(v["front"], (-SX, FY, SZ1), (SX, FY, SZ1), "h", 10), dim(v["right"], (80, FY, GZ0), (80, FY + 4.0, GZ0), "h", -8),
                   leader(v["front"], (SX + 3.1, FY, SZ1), "Port Ø6.15, 0.5 x 45°", 8, 8),
                   leader(v["back"], (63.75, FY, 101.7), "Snap catch (4x)", 14, 10)],
        ["Print front face down. Profile: PLA Grille 0.25 (no expansion).", "Ribs: one 0.5 line, 3.0 pitch, horizontal on layers 1-3,",
         "vertical on layers 4-6. About 69 % open.", "Ports and catches carry the expansion in the model:",
         "ports +0.075 per side, catch posts and bumps +0.095.", "Snap catches: see BSM-09."])
    # strip
    part_sheet("control_strip", "BSM-04", "Control strip", {
        "front": ("front", (0, 0, 18.15), (120, 215), 1.0, False), "back": ("back", (0, 0, 18.15), (120, 160), 1.0, False),
        "top": ("top", (0, 0, 33), (120, 115), 1.0, True), "right": ("right", (0, 0, 18.15), (300, 215), 2.0, True)},
        lambda v: [dim(v["front"], (-PW / 2, FY, 3.3), (PW / 2, FY, 3.3), "h", -8), dim(v["front"], (-PW / 2, FY, 3.3), (-PW / 2, FY, 33), "v", -10),
                   dim(v["front"], (0, FY, 3.3), (POT[0], FY, POT[1]), "h", 12), dim(v["front"], (0, FY, 3.3), (AUX[0], FY, AUX[1]), "h", 20),
                   leader(v["front"], (POT[0] + 4, FY, POT[1]), "Ø8.0", 6, 6), leader(v["front"], (AUX[0] + 5, FY, AUX[1]), "Ø10.0", 4, 8),
                   leader(v["front"], (0, FY, 32.5), "Pry slot 8 x 1", 10, 10), leader(v["front"], (-SX + 3, FY, SZ0), "Port Ø6.0, 0.5 x 45°", 8, 10),
                   leader(v["back"], (-60, FY, 24), "Snap catch (4x)", 10, 10)],
        ["Print front face down. Profile: PLA Parts 0.25. Colour white.", "Snap beam modelled 0.31: with 0.095 expansion it prints one 0.5 line.",
         "Back: two pockets Ø6.5 x 1.0 for the tray screw heads.", "Snap catches: see BSM-09."])
    # rear panel and tray, knob
    part_sheet("rear_panel", "BSM-05", "Rear panel", {
        "back": ("back", (0, 0, H / 2), (120, 185), 1.0, False), "right": ("right", (0, 0, H / 2), (300, 185), 1.0, True)},
        lambda v: [dim(v["back"], (PW / 2, RY, 3.3), (-PW / 2, RY, 3.3), "h", -10), dim(v["back"], (PW / 2, RY, 3.3), (PW / 2, RY, 104.7), "v", -10),
                   dim(v["back"], (SX, RY, SZ0), (-SX, RY, SZ0), "h", -18), leader(v["back"], (44.8 + 5, RY, 21.1), "DC hole Ø10, collar Ø13 x 1.5", 12, -12)],
        ["Print outer face down. Profile: PLA Parts 0.25.", "Four Ø3.4 clearance holes for M3 x 6 socket head cap screws.", "No counterbore: the heads sit on the panel."])
    part_sheet("tray", "BSM-06", "Amplifier tray", {
        "top": ("top", (31.8, 0, 0), (120, 175), 1.5, True), "front": ("front", (31.8, 0, 10), (120, 80), 1.5, True),
        "right": ("right", (31.8, 0, 10), (320, 175), 1.5, True)},
        lambda v: [dim(v["top"], (TX - 61.3 + 3.0, -40, 14), (TX, -40, 14), "h", 12, None),
                   leader(v["front"], (TX, BBY, TZ), "Tab hole: pilot Ø1.6, drill Ø4.0, insert M3 x 3", 10, 18)],
        ["Print flat. Profile: PLA Parts 0.25.", "Rails carry the ZK-502C board 8.0 above the sleeve floor.", "The two tabs screw to the baffle back (M3 x 8)."])
    part_sheet("knob", "BSM-07", "Knob", {
        "front": ("front", (POT[0], -60, POT[1]), (120, 180), 3.0, False), "right": ("right", (POT[0], -60, POT[1]), (300, 180), 3.0, True)},
        lambda v: [dim(v["front"], (POT[0] - 11, -60, POT[1] - 11), (POT[0] + 11, -60, POT[1] - 11), "h", -6),
                   dim(v["right"], (POT[0], -59.8, POT[1] - 11), (POT[0], -47.8, POT[1] - 11), "h", -6)],
        ["Print front face up. Profile: PLA Parts 0.25. Colour orange.", "Bore Ø6.1 x 9.5 for the volume control shaft (check the shaft type).",
         "Glue the white knob mark (1.4 x 1.2 x 5.5) into the groove."])


def joint(names, origin, normal, look, at, page, scale, window, extra, title_y=None):
    """A section view of several parts, clipped to a window around a joint."""
    v = View(look, at, page, scale)
    out = []
    for k, n in enumerate(names):
        s = cut_keep(part(n), origin, normal, window)
        if s is None:
            continue
        out.append(project([s], v, hidden=False))
        out.append(section_hatch(s, v, origin, normal, k))
    out += extra(v)
    return v, "".join(out)


def sheets_joints():
    # BSM-08: front corner screw and tray screw (horizontal sections, seen from above)
    b = []
    w = ((60, -50, SZ1 - 12), (85, -28, SZ1 + 12))
    v1, s1 = joint(["sleeve", "baffle", "grille", "screws_front", "inserts_front"], (0, 0, SZ1), (0, 0, 1), "top", (73, -40, SZ1), (115, 175), 6.0, w,
                   lambda v: [dim(v, (SX - 3, FY, SZ1), (SX + 3, FY, SZ1), "h", 16, "Ø6.0"),
                              dim(v, (SX + 3.6, FY, SZ1), (SX + 3.6, BFY + 1.5, SZ1), "v", 22),
                              dim(v, (SX + 1.7, BFY + 1.5, SZ1), (SX + 1.7, BFY + 1.75, SZ1), "v", 40, "0.25"),
                              dim(v, (80, BBY, SZ1), (80, BBY + 0.4, SZ1), "v", 8, "0.4"),
                              dim(v, (79.7, FY + 2, SZ1), (80, FY + 2, SZ1), "h", 26, "0.3"),
                              balloon(v, (SX, FY, SZ1), 1, -18, 14), balloon(v, (SX + 2.9, FY + 0.9, SZ1), 2, -22, -6),
                              balloon(v, (SX + 2.9, BFY + 0.7, SZ1), 3, -24, -18), balloon(v, (SX + 1.9, BBY + 2, SZ1), 4, 32, -12),
                              balloon(v, (SX + 0.6, BBY + 6.6, SZ1), 5, 30, -22), balloon(v, (80, FY + 0.3, SZ1), 6, 20, 18)])
    b.append(s1)
    b.append(label(115, 262, "SECTION A-A  (Z = 100.5, seen from above)  6:1"))
    b.append(notes(42, 108, ["1  M3 x 8 socket head cap screw, head flush with the grille face",
                             "2  Grille port Ø6.15 (Ø6.0 + 0.075 per side), 0.5 x 45° chamfer",
                             "3  Baffle counterbore Ø6.0 x 1.5, membrane 0.25: drill Ø3.4",
                             "4  Insert M3 x 3 (short), in the sleeve front post",
                             "5  Pilot Ø1.6 with 45° tip: drill Ø4.0 x 7",
                             "6  Sleeve lead-in chamfer 0.6 x 45°; panel fit gap 0.3"], 2.9))
    w2 = ((TX - 9, -50, TZ - 10), (TX + 9, -30, TZ + 10))
    v2, s2 = joint(["baffle", "control_strip", "tray", "screws_tray", "inserts_tray"], (0, 0, TZ), (0, 0, 1), "top", (TX, -40, TZ), (320, 190), 5.0, w2,
                   lambda v: [dim(v, (TX - 3, BFY, TZ), (TX + 3, BFY, TZ), "h", 30, "Ø6.0"),
                              dim(v, (TX + 3.6, BFY, TZ), (TX + 3.6, BFY + 2.25, TZ), "v", 14),
                              dim(v, (TX - 3.25, FY + 0.5, TZ), (TX + 3.25, FY + 0.5, TZ), "h", -36, "Ø6.5"),
                              balloon(v, (TX, BFY - 0.6, TZ), 7, -26, -8), balloon(v, (TX + 1.9, BBY + 2.0, TZ), 8, 26, -14)])
    b.append(s2)
    b.append(label(320, 262, "SECTION E-E  (Z = 13.0)  5:1"))
    b.append(notes(250, 128, ["7  Strip pocket Ø6.5 x 1.0 covers the tray screw head", "   (head 0.75 in front of the baffle, 0.25 clear)",
                              "8  Tray tab: pilot Ø1.6, drill Ø4.0 through, insert M3 x 3", "Counterbore Ø6.0 x 2.25, membrane 0.25"], 2.9))
    sheet("Bluespeaker Mini", "Joint details: front corner and tray screws", "6:1, 5:1", "PLA", "BSM-08", "".join(b))

    # BSM-09: snap catches (vertical sections at the beam centre, seen from the right)
    b = []
    gx, gz = 63.75, 101.7
    wg = ((gx - 3, -49, gz - 6), (gx + 3, -38, gz + 5))
    v3, s3 = joint(["sleeve", "baffle", "grille"], (gx, 0, 0), (1, 0, 0), "right", (gx, -43.5, gz), (110, 175), 9.0, wg,
                   lambda v: [dim(v, (gx, BFY, gz - 1.65), (gx, BFY + 3.0, gz - 1.65), "h", -36),
                              dim(v, (gx, BFY + 1.0, gz + 1.5), (gx, BFY + 1.0, gz + 1.9), "v", 34, "0.4"),
                              dim(v, (gx, FY, gz - 3.0), (gx, BFY, gz - 3.0), "h", -46, "1.5"),
                              dim(v, (gx, BFY + 0.5, gz + 1.0), (gx, BFY + 0.5, gz + 1.5), "v", 46, "0.5"),
                              balloon(v, (gx, BFY + 1.6, gz + 1.25), 1, 30, 24), balloon(v, (gx, BFY + 0.8, gz + 1.85), 2, 40, 12),
                              balloon(v, (gx, BFY + 0.75, gz + 1.68), 3, 44, -2), balloon(v, (gx, BFY + 2.9, gz), 4, 40, -22),
                              balloon(v, (gx, BFY + 0.1, gz - 1.7), 5, -30, -24)])
    b.append(s3)
    b.append(label(110, 268, "SECTION B-B  grille catch (X = 63.75)  9:1"))
    sx_, sz_ = 62.0, 26.0
    ws = ((sx_ - 3, -49, sz_ - 4.5), (sx_ + 3, -38, sz_ + 4))
    v4, s4 = joint(["baffle", "control_strip"], (sx_, 0, 0), (1, 0, 0), "right", (sx_, -43.5, sz_), (310, 185), 9.0, ws,
                   lambda v: [balloon(v, (sx_, BFY + 1.6, sz_ + 1.25), 6, 30, 22), balloon(v, (sx_, BFY + 2.9, sz_), 4, 34, -20)])
    b.append(s4)
    b.append(label(310, 268, "SECTION F-F  strip catch (X = 62.0)  9:1"))
    b.append(notes(42, 66, ["1  Beam: one 0.5 line, 10 long, 2.0 high; bridges 0.5 above the cover back. Flexes in the cover plane.",
                            "2  Bump 0.4 (grille +0.095 comp): 45° catch face, flat 0.25, 18° lead-in",
                            "3  Lip at the pocket mouth: 45°, 0.05 preload on the bump (pulls the cover flat)",
                            "4  Pocket 3.0 deep, 3.3 wide, floor is a bridge. Posts 0.15 clear per side (locate the cover)",
                            "5  Mouth lead-in 0.3 x 45° (takes the elephant foot)",
                            "6  Strip beam modelled 0.31: the Parts profile expansion (0.095) prints one 0.5 line"], 2.9))
    sheet("Bluespeaker Mini", "Joint details: snap catches", "9:1", "PLA", "BSM-09", "".join(b))

    # BSM-10: rear corner and gusset; driver mount
    b = []
    wr = ((SX - 4, 20, SZ1 - 12), (SX + 4, 49, SZ1 + 8))
    v5, s5 = joint(["sleeve", "rear_panel", "screws_rear", "inserts_rear"], (SX, 0, 0), (1, 0, 0), "right", (SX, 36, SZ1 - 2), (110, 180), 4.5, wr,
                   lambda v: [dim(v, (SX, 34, SZ1 - 4), (SX, 44, SZ1 - 4), "h", -40),
                              dim(v, (SX, 26, 105), (SX, 34, 97), "h", 34, "8 at 45°"),
                              balloon(v, (SX, RY, SZ1), 1, 18, 26), balloon(v, (SX, 42.5, SZ1 + 1.8), 2, 12, 34),
                              balloon(v, (SX, 30, 101), 3, -26, 20), balloon(v, (SX, 39, SZ1 - 3.5), 4, -20, -34)])
    b.append(s5)
    b.append(label(110, 268, "SECTION G-G  rear post (X = 75.5)  4.5:1"))
    sp = (63.09, 95.59)
    wsp = ((sp[0] - 9, -48, sp[1] - 9), (sp[0] + 9, -26, sp[1] + 9))
    v6, s6 = joint(["baffle", "grille", "speaker_r", "screws_speaker", "inserts_speaker"], (0, 0, sp[1]), (0, 0, 1), "top", (sp[0], -38, sp[1]),
                   (315, 185), 4.5, wsp, lambda v: [balloon(v, (sp[0] + 1.9, -40.5, sp[1]), 5, 30, 14), balloon(v, (sp[0], -36.7, sp[1]), 6, 32, -12)])
    b.append(s6)
    b.append(label(315, 268, "SECTION H-H  driver mount (Z = 95.59)  4.5:1"))
    b.append(notes(42, 66, ["1  M3 x 6 socket head cap screw; head on the rear panel, Ø3.4 clearance",
                            "2  Insert M3 x 3, printed Ø4.0 hole, 0.5 x 45° relief chamfer",
                            "3  Gussets at 45° to both walls: the post prints with no support",
                            "4  Post 8 x 8, 10 deep",
                            "5  Insert M3 x 3 in the 3 mm spacer frame",
                            "6  M3 x 5 pan head through the driver flange"], 2.9))
    sheet("Bluespeaker Mini", "Joint details: rear post and driver mount", "4.5:1", "PLA", "BSM-10", "".join(b))

    # BSM-11: volume control and AUX
    b = []
    wp = ((POT[0] - 13, -60, POT[1] - 13), (POT[0] + 13, -35, POT[1] + 13))
    v7, s7 = joint(["baffle", "control_strip", "knob", "pot_nut", "amp_parts", "amp_board"], (0, 0, POT[1]), (0, 0, 1), "top", (POT[0], -48, POT[1]),
                   (115, 175), 4.0, wp,
                   lambda v: [dim(v, (POT[0] - 7, BFY, POT[1]), (POT[0] + 7, BFY, POT[1]), "h", 40, "Ø14"),
                              dim(v, (POT[0] + 7.5, BFY, POT[1]), (POT[0] + 7.5, BFY + 2, POT[1]), "v", 14),
                              dim(v, (POT[0] + 11, -59.8, POT[1]), (POT[0] + 11, -47.8, POT[1]), "v", 24),
                              balloon(v, (POT[0] + 3.8, BFY + 2.1, POT[1]), 1, 30, -18), balloon(v, (POT[0] + 4, FY + 0.75, POT[1]), 2, -34, -24)])
    b.append(s7)
    b.append(label(115, 268, "SECTION J-J  volume control (Z = 18.1)  4:1"))
    wa = ((AUX[0] - 9, -50, AUX[1] - 9), (AUX[0] + 9, -36, AUX[1] + 9))
    v8, s8 = joint(["baffle", "control_strip", "amp_parts", "amp_board"], (0, 0, AUX[1]), (0, 0, 1), "top", (AUX[0], -43, AUX[1]), (320, 180), 5.0, wa,
                   lambda v: [dim(v, (AUX[0] - 5, BFY, AUX[1]), (AUX[0] + 5, BFY, AUX[1]), "h", 34, "Ø10"),
                              dim(v, (AUX[0] + 5.5, BFY, AUX[1]), (AUX[0] + 5.5, BFY + 3, AUX[1]), "v", 12),
                              balloon(v, (AUX[0] + 3.3, BFY + 3.1, AUX[1]), 3, 26, -16)])
    b.append(s8)
    b.append(label(320, 268, "SECTION K-K  AUX socket (Z = 15.1)  5:1"))
    b.append(notes(42, 66, ["1  Membrane 0.25 at the floor of the Ø14 x 1.5 nut recess: cut out to Ø7.5",
                            "2  Strip hole Ø8.0; knob Ø22 x 12 with 0.8 gap to the strip",
                            "3  Membrane 0.25 at the floor of the Ø10 x 3 collar counterbore: cut out to Ø6.4",
                            "The ZK-502C positions come from photos. Measure the board before production."], 2.9))
    sheet("Bluespeaker Mini", "Joint details: volume control and AUX socket", "4:1, 5:1", "PLA", "BSM-11", "".join(b))


def main():
    ga()
    sheets_parts()
    sheets_joints()
    write_sheets()


if __name__ == "__main__":
    main()
