"""Two-color control strip for the Bambu Lab X2D: a white strip with gray inlaid labels.

The strip prints front face down. The gray inlay is the first two layers. Both filaments use the
AMS nozzle. Run: uv run --frozen python cad/mini_x2d.py
"""
import json
import math
import os
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

from build123d import BuildSketch, Locations, Mode, Plane, Polygon, RectangleRounded, Rot, export_stl, extrude

sys.path.insert(0, str(Path(__file__).parent))
from bluespeaker_mini import MParams, control_strip  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROFILES = ROOT / "profiles" / "bambu-x2d"
OUT = ROOT / "cad" / "x2d"

INLAY = 0.4  # two 0.20 mm layers
TICKS = 21
TICK_START = 180.0  # degrees clockwise from 12 o'clock: 6 o'clock
TICK_SWEEP = 315.0  # the last bar is at 4:30
TICK_R0, TICK_R1 = 12.2, 14.0  # the knob radius is 11 mm
TICK_W = 0.8  # two lines of the 0.4 mm nozzle
LETTER_H = 4.0  # cap height
STROKE = 0.7  # letter stroke
LETTER_GAP = 0.6
LETTER_W = dict(A=3.0, E=2.2, L=2.0, M=3.8, O=2.6, U=2.5, V=2.7, X=2.8)
AUX_LABEL_Z = 22.9  # above the 10 mm AUX collar
VOLUME_LABEL_X = 69.35  # between the tick ring and the strip edge
VOLUME_LABEL_Z = AUX_LABEL_Z  # above the tray screw pocket, where the front skin is 0.5 mm


def bar(x0, z0, x1, z1):
    Polygon((x0, z0), (x1, z0), (x1, z1), (x0, z1), align=None)


def diagonal(x0, z0, x1, z1):
    """A stroke of width STROKE between two heights, with horizontal ends."""
    half = STROKE * math.hypot(x1 - x0, z1 - z0) / abs(z1 - z0) / 2
    Polygon((x0 - half, z0), (x0 + half, z0), (x1 + half, z1), (x1 - half, z1), align=None)


def letter(ch, x, z):
    """Draw one letter in the active sketch, with its lower left corner at (x, z)."""
    w, h, s = LETTER_W[ch], LETTER_H, STROKE
    inset = s * math.hypot(w / 2, h) / h / 2
    if ch == "A":
        diagonal(x + inset, z, x + w / 2, z + h)
        diagonal(x + w - inset, z, x + w / 2, z + h)
        lift = 1.0 / h
        bar(x + inset + (w / 2 - inset) * lift, z + 1.0, x + w - inset - (w / 2 - inset) * lift, z + 1.0 + s)
    elif ch == "E":
        bar(x, z, x + s, z + h)
        bar(x, z, x + w, z + s)
        bar(x, z + (h - s) / 2, x + w - 0.3, z + (h + s) / 2)
        bar(x, z + h - s, x + w, z + h)
    elif ch == "L":
        bar(x, z, x + s, z + h)
        bar(x, z, x + w, z + s)
    elif ch == "M":
        bar(x, z, x + s, z + h)
        bar(x + w - s, z, x + w, z + h)
        diagonal(x + s / 2, z + h, x + w / 2, z + 1.0)
        diagonal(x + w - s / 2, z + h, x + w / 2, z + 1.0)
    elif ch == "O":
        with Locations((x + w / 2, z + h / 2)):
            RectangleRounded(w, h, w / 2 - 0.01)
            RectangleRounded(w - 2 * s, h - 2 * s, w / 2 - s - 0.01, mode=Mode.SUBTRACT)
    elif ch == "U":
        r, steps = w / 2, 16
        outer = [(x + r - r * math.cos(math.pi * i / steps), z + r - r * math.sin(math.pi * i / steps))
                 for i in range(steps + 1)]
        inner = [(x + r - (r - s) * math.cos(math.pi * i / steps), z + r - (r - s) * math.sin(math.pi * i / steps))
                 for i in range(steps, -1, -1)]
        Polygon((x, z + h), *outer, (x + w, z + h), (x + w - s, z + h), *inner, (x + s, z + h), align=None)
    elif ch == "V":
        diagonal(x + inset, z + h, x + w / 2, z)
        diagonal(x + w - inset, z + h, x + w / 2, z)
    elif ch == "X":
        diagonal(x + inset, z, x + w - inset, z + h)
        diagonal(x + w - inset, z, x + inset, z + h)


def word(text, cx, cz):
    """Draw a word in the active sketch, centered on (cx, cz)."""
    x = cx - (sum(LETTER_W[c] for c in text) + LETTER_GAP * (len(text) - 1)) / 2
    for c in text:
        letter(c, x, cz - LETTER_H / 2)
        x += LETTER_W[c] + LETTER_GAP


def labels(p: MParams):
    """The gray inlay, in assembly coordinates."""
    kx, kz = p.pot
    ax, _ = p.aux
    with BuildSketch(Plane.XZ.offset(-(p.front_y + INLAY))) as sk:
        for i in range(TICKS):
            a = math.radians(TICK_START + TICK_SWEEP * i / (TICKS - 1))
            ux, uz = math.sin(a), math.cos(a)
            tx, tz = uz * TICK_W / 2, -ux * TICK_W / 2
            Polygon(*[(kx + r * ux + s * tx, kz + r * uz + s * tz)
                      for r, s in ((TICK_R0, -1), (TICK_R0, 1), (TICK_R1, 1), (TICK_R1, -1))], align=None)
        word("AUX", ax, AUX_LABEL_Z)
        word("VOLUME", VOLUME_LABEL_X, VOLUME_LABEL_Z)
    return extrude(sk.sketch, amount=INLAY)


def read_stl(path):
    """The vertices and triangles of a binary STL, with equal vertices welded."""
    data = Path(path).read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    verts, index, tris = [], {}, []
    for i in range(count):
        values = struct.unpack_from("<9f", data, 84 + 50 * i + 12)
        tri = []
        for j in range(0, 9, 3):
            v = tuple(round(c, 4) for c in values[j:j + 3])
            if v not in index:
                index[v] = len(verts)
                verts.append(v)
            tri.append(index[v])
        if len(set(tri)) == 3:
            tris.append(tri)
    return verts, tris


def mesh_xml(mesh, oid, name, filament, walls, z0, cx, cy):
    """One 3MF object. The zslice settings keep the two parts apart: joined parts print as paint,
    and paint on a bottom face goes through the full bottom thickness."""
    verts, tris = mesh
    meta = (f'<metadatagroup><metadata name="zslice:project.filament">{filament}</metadata>'
            f'<metadata name="zslice:project.wall_count">{walls}</metadata></metadatagroup>')
    vx = "".join(f'<vertex x="{x - cx:.4f}" y="{y - cy:.4f}" z="{z - z0:.4f}"/>' for x, y, z in verts)
    tx = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tris)
    return f'<object id="{oid}" name="{name}" type="model">{meta}<mesh><vertices>{vx}</vertices><triangles>{tx}</triangles></mesh></object>'


def write_source_3mf(path, white, gray):
    """Two build items at one place. Filament 1 is white and filament 2 is gray."""
    w, g = read_stl(white), read_stl(gray)
    xs, ys, zs = zip(*w[0])
    z0, cx, cy = min(zs), (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    place = 'transform="1 0 0 0 1 0 0 0 1 128 128 0"'
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             f'<resources>{mesh_xml(w, 1, "white", 1, 4, z0, cx, cy)}{mesh_xml(g, 2, "gray", 2, 2, z0, cx, cy)}</resources>'
             f'<build><item objectid="1" {place}/><item objectid="2" {place}/></build></model>')
    colors = json.dumps({"filament_colour": ["#FFFFFF", "#8E9089"], "filament_type": ["PLA", "PLA"]})
    types = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
             '<Default Extension="config" ContentType="text/plain"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in (("[Content_Types].xml", types), ("_rels/.rels", rels), ("3D/3dmodel.model", model),
                           ("Metadata/project_settings.config", colors)):
            z.writestr(zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)), text, zipfile.ZIP_DEFLATED)


def main():
    # The X2D profile has no horizontal expansion, so the snap beam keeps its full 0.5 mm width.
    p = MParams(parts_xy=0.0)
    strip = control_strip(p)
    inlay = labels(p)
    white = strip - inlay
    gray = strip & inlay
    lost = inlay.volume - gray.volume
    if lost > 0.001:
        raise SystemExit(f"The inlay is outside the strip by {lost:.3f} mm^3")
    bb = inlay.bounding_box()
    print(f"inlay {inlay.volume:.1f} mm^3, X {bb.min.X:.2f}..{bb.max.X:.2f}, Z {bb.min.Z:.2f}..{bb.max.Z:.2f}, solids {len(gray.solids())}")
    print(f"white valid {white.is_valid}, solids {len(white.solids())}")
    OUT.mkdir(exist_ok=True)
    white_stl, gray_stl = OUT / "control_strip_white.stl", OUT / "control_strip_gray.stl"
    export_stl(Rot(90, 0, 0) * white, white_stl, tolerance=0.01, angular_tolerance=0.1)
    export_stl(Rot(90, 0, 0) * gray, gray_stl, tolerance=0.01, angular_tolerance=0.1)
    src = OUT / "control_strip_source.3mf"
    write_source_3mf(src, white_stl, gray_stl)
    zslice = os.environ.get("ZSLICE")
    if not zslice:
        print("Set ZSLICE to bin/zslice.mjs of zslice 0.5.0-beta to write the print file.")
        return 0
    profiles = PROFILES / "zslice"
    cmd = ["node", zslice, "slice", str(src), "-m", str(profiles / "machine/bambu-lab-x2d.toml"),
           "-f", str(profiles / "filament/white-gray.toml"), "-p", str(profiles / "project/pla-0.20-inlay.toml"),
           "-o", os.devnull, "--bambu", str(OUT / "control_strip_x2d.gcode.3mf"), "--stats", "-"]
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
