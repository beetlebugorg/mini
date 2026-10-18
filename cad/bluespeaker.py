"""Parametric enclosure model for the Bluespeaker.

Coordinates: X is width (left to right), Y is depth (front is -Y), Z is
height (the floor is Z = 0). All units are mm.

Usage:
    uv run cad/bluespeaker.py --export   # write GLB, STL, and manifest
    uv run cad/bluespeaker.py --show     # send to OCP CAD Viewer
    uv run cad/bluespeaker.py --check    # report parts that collide
"""

import argparse
import itertools
import json
import math
import struct
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from build123d import (
    Align,
    Axis,
    Box,
    BuildSketch,
    Circle,
    Compound,
    Cone,
    Cylinder,
    GridLocations,
    Location,
    Locations,
    Mode,
    Plane,
    PolarLocations,
    Pos,
    Rectangle,
    RectangleRounded,
    Rot,
    Vector,
    export_gltf,
    export_stl,
    extrude,
    fillet,
    import_step,
    loft,
)

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "cad" / "vendor"
MIN = (Align.CENTER, Align.CENTER, Align.MIN)


@dataclass
class Params:
    # Shell
    width: float = 260.0
    height: float = 165.0
    depth: float = 120.0
    wall: float = 4.0
    edge_r: float = 4.0
    grille_t: float = 2.0
    baffle_t: float = 6.0
    rear_t: float = 6.0
    strip_top: float = 56.0  # Z of the top of the control strip
    seam: float = 0.5
    fit: float = 0.2  # clearance on each side of a part that fits in the sleeve

    # Grille
    hole_d: float = 3.0
    hole_pitch: float = 4.5
    grille_side: float = 4.0  # solid border at the sides
    grille_band: float = 8.0  # solid band at the top and bottom (magnets)

    # Drivers: Dayton Audio ND90-4, rear-mounted on a spacer frame
    driver_x: float = 70.0
    driver_z: float = 108.5
    driver_cut: float = 83.0
    driver_spacer: float = 4.0
    pr_x: float = 58.0
    pr_z: float = 56.0
    pr_cut: float = 83.0
    pr_spacer: float = 3.0
    flange: float = 88.5  # square frame of the ND90-4 and ND90-PR
    flange_holes: float = 33.0  # hole offset from the axis, X and Z

    # Control strip
    lcd_x: float = -77.0
    lcd_win: tuple = (62.0, 44.0)  # acrylic window in the strip
    lcd_open: tuple = (51.0, 39.0)  # opening in the baffle (active area + 1 mm)
    lcd_panel: tuple = (60.26, 42.72)  # 2.4 in TFT outline
    lcd_carrier: tuple = (73.0, 44.0)
    lcd_holes: tuple = (34.0, 18.5)  # carrier hole offsets
    key_x: tuple = (-18.0, 0.0, 18.0)
    key_d: float = 12.0
    knob_x: float = 92.0
    knob_d: float = 30.0
    knob_h: float = 14.0
    knob_gap: float = 1.0

    # Electronics
    pcb_w: float = 224.0
    pcb_h: float = 46.0
    pcb_t: float = 1.6
    pcb_x: float = 0.0
    pcb_front_y: float = -42.0
    pcb_bosses: tuple = ((-32.0, -18.0), (-32.0, 18.0), (60.0, -18.0), (60.0, 18.0))
    bay_wall_y: float = -12.0
    cell_d: float = 21.0
    cell_l: float = 70.0
    usb_z: float = 145.0

    # Fasteners
    post: float = 11.0  # square sleeve posts for the panel screws
    insert_hole: float = 4.0  # M3 heat-set insert, 5.7 mm long
    insert_depth: float = 6.5

    @property
    def inner_w(self):
        return self.width - 2 * self.wall

    @property
    def inner_h(self):
        return self.height - 2 * self.wall

    @property
    def panel_w(self):
        return self.inner_w - 2 * self.fit

    @property
    def panel_h(self):
        return self.inner_h - 2 * self.fit

    @property
    def front_y(self):
        return -self.depth / 2

    @property
    def rear_y(self):
        return self.depth / 2

    @property
    def baffle_front_y(self):
        return self.front_y + self.grille_t

    @property
    def baffle_back_y(self):
        return self.baffle_front_y + self.baffle_t

    @property
    def driver_mount_y(self):
        return self.baffle_back_y + self.driver_spacer

    @property
    def rear_inner_y(self):
        return self.rear_y - self.rear_t

    @property
    def pr_mount_y(self):
        return self.rear_inner_y - self.pr_spacer

    @property
    def strip_zc(self):
        return (self.wall + self.strip_top) / 2

    @property
    def inner_zc(self):
        return self.height / 2

    @property
    def post_c(self):
        """X of the corner posts and Z of the bottom and top posts."""
        x = self.width / 2 - self.wall - self.post / 2
        return x, self.wall + self.post / 2, self.height - self.wall - self.post / 2

    @property
    def battery_axis(self):
        return self.bay_wall_y - self.cell_d / 2 - 2.0, 20.0

    @property
    def usb_board_top(self):
        return self.usb_z - 1.73


# --------------------------------------------------------------------- helpers


def put(s, x=None, y=None, z=None, xmin=None, ymin=None, ymax=None, zmin=None):
    """Move a shape so that its bounding box meets the given values."""
    bb = s.bounding_box()
    c = bb.center()
    dx = dy = dz = 0.0
    if x is not None:
        dx = x - c.X
    if xmin is not None:
        dx = xmin - bb.min.X
    if y is not None:
        dy = y - c.Y
    if ymin is not None:
        dy = ymin - bb.min.Y
    if ymax is not None:
        dy = ymax - bb.max.Y
    if z is not None:
        dz = z - c.Z
    if zmin is not None:
        dz = zmin - bb.min.Z
    return Pos(dx, dy, dz) * s


def orient(shape, origin, x_dir, z_dir):
    """Place a shape so that its local X and Z axes point along x_dir and z_dir."""
    return Location(Plane(origin=origin, x_dir=x_dir, z_dir=z_dir)) * shape


def along(shape, at, direction):
    """Place a shape built along +Z so that +Z points along direction."""
    d = Vector(*direction).normalized()
    x = Vector(0, 1, 0) if abs(d.X) > 0.9 else Vector(1, 0, 0)
    return orient(shape, at, x, d)


def merge(shapes):
    out = shapes[0]
    for s in shapes[1:]:
        out = out + s
    return out


@cache
def vendor(name):
    return import_step(str(VENDOR / name))


# ------------------------------------------------------------------ fasteners


@dataclass
class Fastener:
    """One screw joint.

    'at' is the point where the screw enters the first part. 'dir' points
    into the material. The tool cuts a countersink or nothing for the head,
    a clearance hole for 'through' mm, then an insert or pilot hole.
    """

    group: str
    kind: str  # "csk3", "pan3", "pan25"
    at: tuple
    dir: tuple
    through: float
    cut: tuple  # names of the parts that the tool cuts
    insert: bool = True
    clear_d: float = 3.4


def screw_len(f: Fastener):
    if f.kind == "csk3":
        return 10.0
    return 6.0


def fasteners(p: Params):
    fs = []
    px, pz0, pz1 = p.post_c
    # Baffle to the sleeve, and baffle to the bay wall tabs (front, under the covers)
    for x, z in [(-px, pz0), (px, pz0), (-px, pz1), (px, pz1), (0, pz1)]:
        fs.append(Fastener("baffle", "csk3", (x, p.baffle_front_y, z), (0, 1, 0), p.baffle_t, ("baffle", "sleeve")))
    for x in bay_tab_x(p):
        fs.append(Fastener("bay", "csk3", (x, p.baffle_front_y, bay_tab_z(p)), (0, 1, 0), p.baffle_t, ("baffle", "bay_wall")))
    # Rear panel to the sleeve
    for x, z in [(-px, pz0), (px, pz0), (-px, pz1), (px, pz1), (0, pz0), (0, pz1)]:
        fs.append(Fastener("rear", "csk3", (x, p.rear_y, z), (0, -1, 0), p.rear_t, ("rear_panel", "sleeve")))
    # Drivers: screw head on the back of the flange, insert in the spacer frame
    h = p.flange_holes
    for sx in (-1, 1):
        for i, j in itertools.product((-1, 1), (-1, 1)):
            at = (sx * p.driver_x + i * h, p.driver_mount_y + 1.0, p.driver_z + j * h)
            fs.append(Fastener("driver", "pan3", at, (0, -1, 0), 1.0, ("baffle",)))
            at = (sx * p.pr_x + i * h, p.pr_mount_y - 1.0, p.pr_z + j * h)
            fs.append(Fastener("radiator", "pan3", at, (0, 1, 0), 1.0, ("rear_panel",)))
    # Main PCB to the baffle bosses
    back = p.pcb_front_y + p.pcb_t
    for bx, bz in p.pcb_bosses:
        fs.append(Fastener("pcb", "pan3", (bx, back, p.strip_zc + bz), (0, -1, 0), p.pcb_t, ("pcb_board", "baffle")))
    # LCD carrier to the baffle posts (M2.5 thread-forming screws)
    cy = lcd_carrier_back_y(p)
    hx, hz = p.lcd_holes
    for i, j in itertools.product((-1, 1), (-1, 1)):
        at = (p.lcd_x + i * hx, cy, p.strip_zc + j * hz)
        fs.append(Fastener("lcd", "pan25", at, (0, -1, 0), 1.6, ("lcd_carrier", "baffle"), insert=False, clear_d=2.8))
    # Encoder board to the back of the baffle (M2.5 thread-forming screws)
    for dx, dz in [(8.5, 7.0), (-8.5, -7.0)]:
        at = (p.knob_x + dx, p.baffle_back_y + 1.6, p.strip_zc + dz)
        fs.append(Fastener("encoder", "pan25", at, (0, -1, 0), 1.6, ("enc_board", "baffle"), insert=False, clear_d=2.8))
    # USB-C port board to the shelf on the rear panel (M2.5 thread-forming screws)
    for x in (-8.0, 8.0):
        at = (x, port_board_y(p)[0] + 4.0, p.usb_board_top)
        fs.append(Fastener("port", "pan25", at, (0, 0, -1), 1.6, ("port_board", "rear_panel"), insert=False, clear_d=2.8))
    return fs


def fastener_tool(f: Fastener, p: Params):
    """Solid that cuts the holes for one fastener (built along +Z, then placed)."""
    parts = [Cylinder(f.clear_d / 2, f.through + 0.01, align=MIN)]
    if f.kind == "csk3":
        parts.append(Cone(3.4, 1.6, 1.8, align=MIN))
    if f.insert:
        parts.append(Pos(0, 0, f.through) * Cylinder(p.insert_hole / 2, p.insert_depth, align=MIN))
    else:
        parts.append(Pos(0, 0, f.through) * Cylinder(1.0, 5.0, align=MIN))
    return along(merge(parts), f.at, f.dir)


def screw_model(f: Fastener):
    L = screw_len(f)
    r = 1.5 if f.kind != "pan25" else 1.25
    shank = Cylinder(r, L, align=MIN)
    if f.kind == "csk3":
        head = Cone(3.0, 1.5, 1.7, align=MIN)
        head = head - Pos(0, 0, -0.01) * Box(3.4, 0.7, 1.2, align=MIN)
        s = head + shank
    else:
        hr = 2.75 if r == 1.5 else 2.25
        head = Pos(0, 0, -2.0) * Cylinder(hr, 2.0, align=MIN)
        head = fillet(head.edges().group_by(Axis.Z)[0], 0.6)
        s = head + shank
    return along(s, f.at, f.dir)


def insert_model(f: Fastener):
    # drawn at the hole diameter; the real knurl cuts 0.3 mm into the plastic
    body = Cylinder(1.99, 5.7, align=MIN) - Cylinder(1.5, 5.8, align=MIN)
    d = Vector(*f.dir).normalized()
    at = Vector(*f.at) + d * f.through
    return along(body, at, f.dir)


@dataclass
class Magnet:
    group: str
    at: tuple
    dir: tuple  # into the part that holds the deep pocket
    d: float = 6.0
    t: float = 2.0


def magnets(p: Params):
    ms = []
    y = p.baffle_front_y
    z_lo = p.strip_top + p.seam + p.grille_band / 2
    z_hi = p.height - p.wall - p.fit - p.grille_band / 2
    for x in (-100.0, 100.0):
        for z in (z_lo, z_hi):
            ms.append(Magnet("grille", (x, y, z), (0, 1, 0)))
    for x in (-114.0, 114.0):
        for z in (p.strip_zc - 18, p.strip_zc + 18):
            ms.append(Magnet("strip", (x, y, z), (0, 1, 0)))
    return ms


def magnet_pocket(m: Magnet, depth, extra=0.2):
    return along(Cylinder(m.d / 2 + 0.1, depth + extra, align=MIN), m.at, m.dir)


# ---------------------------------------------------------------- printed parts


def bay_tab_x(p: Params):
    return (-119.0, 0.0, 119.0)


def bay_tab_z(p: Params):
    return p.strip_top + 4.0


def lcd_carrier_back_y(p: Params):
    return p.baffle_back_y + 3.9 + p.pcb_t


def port_board_y(p: Params):
    return p.rear_inner_y - 16.0, p.rear_inner_y - 0.3


def post_gusset(x, z, s, y_end, wall_x, wall_z):
    """45-degree gusset under a square sleeve post, for printing front opening down.

    y_end is the post face that points to the bed (-Y). wall_x and wall_z are
    -1, 0, or +1: the side of the post that touches a wall (0: no wall on that
    axis). The gusset is one wedge for each wall. Each wedge starts along the
    full width of the post on the wall face and grows at exactly 45 degrees.
    Each layer therefore makes the wall a little thicker along its full
    length. No layer is a small island, and the slicer adds no supports.
    """
    ov = 0.5  # the thin edge of each wedge goes this far into the wall
    apex_plane = Plane.XZ.offset(-(y_end - s))  # s towards the bed
    base_plane = Plane.XZ.offset(-y_end)
    base = base_plane * Pos(x, z) * Rectangle(s, s)
    wedges = []
    if wall_x:
        wedges.append(loft([apex_plane * Pos(x + wall_x * (s + ov) / 2, z) * Rectangle(ov, s), base]))
    if wall_z:
        wedges.append(loft([apex_plane * Pos(x, z + wall_z * (s + ov) / 2) * Rectangle(s, ov), base]))
    return merge(wedges)


def sleeve(p: Params, fs):
    outer = RectangleRounded(p.width, p.height, p.edge_r)
    inner = RectangleRounded(p.inner_w, p.inner_h, 0.5)
    body = put(extrude(Plane.XZ * (outer - inner), amount=p.depth), x=0, ymin=p.front_y, zmin=0)

    px, pz0, pz1 = p.post_c
    s = p.post
    posts = []
    for x, z in [(-px, pz0), (px, pz0), (-px, pz1), (px, pz1), (0, pz1)]:
        posts.append(Pos(x, p.baffle_back_y + 6, z) * Box(s, 12, s))
    for x, z in [(-px, pz0), (px, pz0), (-px, pz1), (px, pz1), (0, pz0), (0, pz1)]:
        post = Pos(x, p.rear_inner_y - 6, z) * Box(s, 12, s)
        # 45 degree gusset from the wall, so the post prints without supports
        wall_x = 0 if x == 0 else (1 if x > 0 else -1)
        wall_z = -1 if z == pz0 else 1
        posts.append(post + post_gusset(x, z, s, p.rear_inner_y - 12, wall_x, wall_z))
    body = body + merge(posts)

    # brace pockets, feet recesses
    for sx in (-1, 1):
        body = body - Pos(sx * (p.inner_w / 2 + 1), 30, 140) * Box(2.2, 8.4, 8.4)
    for sx, sy in itertools.product((-1, 1), (-1, 1)):
        body = body - Pos(sx * 110, sy * 44, -0.01) * Cylinder(6.2, 1.0, align=MIN)
    return cut_fasteners(body, "sleeve", fs, p)


def brace(p: Params):
    return Pos(0, 30, 140) * Box(p.inner_w + 4 - 0.4, 8, 8)


def grille(p: Params):
    z0, z1 = p.strip_top + p.seam, p.height - p.wall - p.fit
    h = z1 - z0
    hz = h - 2 * p.grille_band
    nx = int((p.panel_w - 2 * p.grille_side - p.hole_d) // p.hole_pitch) + 1
    nz = int((hz - p.hole_d) // p.hole_pitch) + 1
    with BuildSketch(Plane.XZ) as sk:
        RectangleRounded(p.panel_w, h, 1.0)
        with GridLocations(p.hole_pitch, p.hole_pitch, nx, nz):
            Circle(p.hole_d / 2, mode=Mode.SUBTRACT)
    g = put(extrude(sk.sketch, amount=p.grille_t), x=0, ymin=p.front_y, z=(z0 + z1) / 2)
    for m in magnets(p):
        if m.group == "grille":
            g = g - along(Cylinder(3.1, 1.1, align=MIN), m.at, (0, -1, 0))
    return g


def control_strip(p: Params):
    h = p.strip_top - p.wall - p.fit
    with BuildSketch(Plane.XZ) as sk:
        RectangleRounded(p.panel_w, h, 1.0)
        with Locations((p.lcd_x, 0)):
            Rectangle(*p.lcd_win, mode=Mode.SUBTRACT)
        with Locations(*[(kx, 0) for kx in p.key_x]):
            Circle(p.key_d / 2 + 0.3, mode=Mode.SUBTRACT)
        with Locations((p.knob_x, 0)):
            Circle(4.0, mode=Mode.SUBTRACT)
    s = put(extrude(sk.sketch, amount=p.grille_t), x=0, ymin=p.front_y, zmin=p.wall + p.fit)
    s = s - Pos(p.knob_x, p.baffle_front_y - 0.4, p.strip_zc) * Box(12.6, 0.81, 12.6)  # encoder body recess
    for m in magnets(p):
        if m.group == "strip":
            s = s - along(Cylinder(3.1, 1.1, align=MIN), m.at, (0, -1, 0))
    return s


def baffle(p: Params, fs):
    zc = p.inner_zc
    sz = p.strip_zc - zc
    with BuildSketch(Plane.XZ) as sk:
        RectangleRounded(p.panel_w, p.panel_h, 1.0)
        with Locations((p.lcd_x, sz)):
            Rectangle(*p.lcd_open, mode=Mode.SUBTRACT)
        with Locations(*[(kx, sz) for kx in p.key_x]):
            Circle(p.key_d / 2 + 0.3, mode=Mode.SUBTRACT)
        with Locations((p.knob_x, sz)):
            Rectangle(12.6, 12.6, mode=Mode.SUBTRACT)  # encoder body pocket
    b = put(extrude(sk.sketch, amount=p.baffle_t), x=0, ymin=p.baffle_front_y, z=zc)

    # spacer frames for the drivers, PCB bosses, LCD posts
    adds = []
    for sx in (-1, 1):
        frame = extrude(Plane.XZ * RectangleRounded(p.flange + 1.5, p.flange + 1.5, 24), amount=p.driver_spacer)
        adds.append(put(frame, x=sx * p.driver_x, ymin=p.baffle_back_y, z=p.driver_z))
    for bx, bz in p.pcb_bosses:
        boss = Cylinder(3.5, p.pcb_front_y - p.baffle_back_y, align=MIN)
        adds.append(along(boss, (bx, p.baffle_back_y, p.strip_zc + bz), (0, 1, 0)))
    hx, hz = p.lcd_holes
    for i, j in itertools.product((-1, 1), (-1, 1)):
        post = Cylinder(2.5, 3.9, align=MIN)
        adds.append(along(post, (p.lcd_x + i * hx, p.baffle_back_y, p.strip_zc + j * hz), (0, 1, 0)))
    b = b + merge(adds)

    # driver holes with a 45 degree flare at the front
    for sx in (-1, 1):
        c = (sx * p.driver_x, p.baffle_front_y - 0.01, p.driver_z)
        hole = Cylinder(p.driver_cut / 2, p.baffle_t + p.driver_spacer + 0.1, align=MIN)
        flare = Cone(p.driver_cut / 2 + 3, p.driver_cut / 2, 3, align=MIN)
        b = b - along(hole + flare, c, (0, 1, 0))

    for f in fs:
        if "baffle" in f.cut:
            b = b - fastener_tool(f, p)
    for m in magnets(p):
        b = b - magnet_pocket(m, m.t)
    return b


def rear_panel(p: Params, fs):
    zc = p.inner_zc
    with BuildSketch(Plane.XZ) as sk:
        RectangleRounded(p.panel_w, p.panel_h, 1.0)
        with Locations((0, p.usb_z - zc)):
            RectangleRounded(9.8, 3.8, 1.0, mode=Mode.SUBTRACT)
    r = put(extrude(sk.sketch, amount=p.rear_t), x=0, ymax=p.rear_y, z=zc)

    adds = []
    for sx in (-1, 1):
        frame = extrude(Plane.XZ * RectangleRounded(p.flange + 1.5, p.flange + 1.5, 24), amount=p.pr_spacer)
        adds.append(put(frame, x=sx * p.pr_x, ymax=p.rear_inner_y, z=p.pr_z))
    # shelf for the USB-C port board
    y0, y1 = port_board_y(p)
    shelf_top = p.usb_board_top - 1.6
    adds.append(Pos(0, (y0 + p.rear_inner_y) / 2, shelf_top - 1.5) * Box(26, p.rear_inner_y - y0, 3))
    r = r + merge(adds)

    for sx in (-1, 1):
        c = (sx * p.pr_x, p.rear_y + 0.01, p.pr_z)
        hole = Cylinder(p.pr_cut / 2, p.rear_t + p.pr_spacer + 0.1, align=MIN)
        flare = Cone(p.pr_cut / 2 + 3, p.pr_cut / 2, 3, align=MIN)
        r = r - along(hole + flare, c, (0, -1, 0))
    for f in fs:
        if "rear_panel" in f.cut:
            r = r - fastener_tool(f, p)
    return r


def bay_wall(p: Params, fs):
    floor = p.wall
    w = p.inner_w - 2
    wall = Pos(0, p.bay_wall_y + 1.5, floor) * Box(w, 3, p.strip_top - 3 - floor, align=MIN)
    shelf_d = p.bay_wall_y + 3 - p.baffle_back_y
    shelf = Pos(0, p.baffle_back_y + shelf_d / 2, p.strip_top - 3) * Box(w, shelf_d, 3, align=MIN)
    tabs = [Pos(x, p.baffle_back_y + 4, p.strip_top) * Box(8, 8, 8, align=MIN) for x in bay_tab_x(p)]
    # battery saddles with strap slots
    by, bz = p.battery_axis
    s0, s1 = by - 9.0, p.bay_wall_y
    saddles = [Pos(x, (s0 + s1) / 2, floor) * Box(14, s1 - s0, bz - floor, align=MIN) for x in (-90.0, 0.0, 90.0)]
    b = merge([wall, shelf, *tabs, *saddles])
    cells = Pos(0, by, bz) * Rot(0, 90, 0) * Cylinder(p.cell_d / 2 + 0.4, 3 * p.cell_l + 20)
    b = b - cells
    for x in (-90.0, 90.0):
        b = b - Pos(x, (s0 + s1) / 2, floor + 1.0) * Box(10.5, s1 - s0 + 1, 2.5, align=MIN)
    # cable holes in the shelf: two speaker leads and the USB-C cable
    for x in (-70.0, 0.0, 70.0):
        b = b - Pos(x, -25, p.strip_top - 3.5) * Cylinder(4, 4, align=MIN)
    for f in fs:
        if "bay_wall" in f.cut:
            b = b - fastener_tool(f, p)
    return b


def knob(p: Params):
    with BuildSketch(Plane.XZ) as sk:
        Circle(p.knob_d / 2)
        with PolarLocations(p.knob_d / 2, 48):
            Circle(0.8, mode=Mode.SUBTRACT)
    k = put(extrude(sk.sketch, amount=p.knob_h), x=p.knob_x, ymax=p.front_y - p.knob_gap, z=p.strip_zc)
    # D-shaft bore, 6 mm with a 4.5 mm flat, 11.5 mm deep
    bore = Cylinder(3.05, 11.5, align=MIN) - Pos(0, 1.55 + 1.5, 0) * Box(6.2, 3.0, 30)
    k = k - along(bore, (p.knob_x, p.front_y - p.knob_gap + 0.01, p.strip_zc), (0, -1, 0))
    # counterbore for the encoder bushing (7 mm), 5.2 mm deep
    k = k - along(Cylinder(3.9, 5.2, align=MIN), (p.knob_x, p.front_y - p.knob_gap + 0.01, p.strip_zc), (0, -1, 0))
    return k - knob_mark(p)


def knob_mark(p: Params):
    y = p.front_y - p.knob_gap - p.knob_h + 0.6
    return Pos(p.knob_x, y, p.strip_zc + 10.5) * Box(1.6, 1.2, 7)


def key(p: Params, kx: float):
    stem_l = 11.0
    stem = Cylinder(2.5, stem_l, align=MIN)
    flange = Pos(0, 0, 1) * Cylinder(p.key_d / 2 + 1.6, 1, align=MIN)
    cap = Cylinder(p.key_d / 2, 5.5, align=MIN)
    cap = fillet(cap.edges().group_by(Axis.Z)[-1], 2.5)
    k = stem + flange + Pos(0, 0, stem_l) * cap
    return along(k, (kx, p.pcb_front_y - 5.0, p.strip_zc), (0, -1, 0))


def feet(p: Params):
    fs = [Pos(sx * 110, sy * 44, -3) * Cylinder(6, 3.9, align=MIN) for sx in (-1, 1) for sy in (-1, 1)]
    return Compound(children=fs)


def lcd_window(p: Params):
    w, h = p.lcd_win
    return Pos(p.lcd_x, p.front_y + 0.75, p.strip_zc) * Box(w - 0.4, 1.5, h - 0.4)


# -------------------------------------------------------------- bought parts


def driver(p: Params, sx: int):
    # Dayton STEP: axis +Y is the front, the flange front face is at Y = 1.
    d = vendor("dayton/nd90/ND90-4 and -8.step")
    return Pos(sx * p.driver_x, p.driver_mount_y + 1.0, p.driver_z) * Rot(0, 0, 180) * d


def radiator(p: Params, sx: int):
    r = vendor("dayton/nd90pr/ND90-PR.step")
    return Pos(sx * p.pr_x, p.pr_mount_y - 1.0, p.pr_z) * r


def cut_fasteners(shape, name, fs, p):
    for f in fs:
        if name in f.cut:
            shape = shape - fastener_tool(f, p)
    return shape


@cache
def kicad_step(name):
    return import_step(str(ROOT / "pcb" / "out" / f"{name}.step"))


def kicad_pcb(p: Params, name):
    """Main PCB from KiCad (pcb/export.sh). STEP: +X right and +Y up on the top side, +Z out of the top side.

    The top side faces the rear (+Y). Seen from the rear, KiCad +X is enclosure -X.
    """
    return orient(kicad_step(name), (p.pcb_x, p.pcb_front_y, p.strip_zc), (-1, 0, 0), (0, 1, 0))


def enc_board(p: Params, fs):
    """Encoder daughter board, flat on the back of the baffle at the knob."""
    b = Pos(p.knob_x, p.baffle_back_y + 0.8, p.strip_zc) * Box(22, 1.6, 22)
    b = fillet(b.edges().filter_by(Axis.Y), 1.0)
    return cut_fasteners(b, "enc_board", fs, p)


def encoder(p: Params):
    """EC11E encoder with a 20 mm D-shaft (shaft top 20 mm from the board), for example Alps EC11E15244G1.

    The body sits in a pocket through the baffle. The bushing goes through the
    control strip into a counterbore in the knob.
    """
    front = p.baffle_back_y  # front face of the encoder board
    zc = p.strip_zc
    body = Pos(p.knob_x, front - 3.25, zc) * Box(11.7, 6.5, 12)
    bushing = along(Cylinder(3.5, 7, align=MIN), (p.knob_x, front - 6.5, zc), (0, -1, 0))
    shaft_l = 20.0 - 13.5
    shaft = Cylinder(3.0, shaft_l, align=MIN) - Pos(0, 1.5, 0) * Box(6.2, 3.0, shaft_l + 0.1, align=(Align.CENTER, Align.MIN, Align.MIN))
    shaft = along(shaft, (p.knob_x, front - 13.5, zc), (0, -1, 0))
    pins = [Pos(p.knob_x + dx, front + 1.6 + 1.5, zc + dz) * Box(0.8, 3.0, 0.8)
            for dx, dz in [(-2.5, -7.5), (0, -7.5), (2.5, -7.5), (-2.5, 7.0), (2.5, 7.0)]]
    return merge([body, bushing, shaft, *pins])


def lcd_panel(p: Params):
    w, h = p.lcd_panel
    y0 = p.baffle_back_y
    glass = Pos(p.lcd_x, y0 + 1.1, p.strip_zc) * Box(w, 2.2, h)
    return fillet(glass.edges().filter_by(Axis.Y), 0.5)


def lcd_backlight(p: Params):
    w, h = p.lcd_panel
    return Pos(p.lcd_x, p.baffle_back_y + 2.2 + 0.85, p.strip_zc) * Box(w, 1.7, h)


def lcd_carrier(p: Params, fs):
    w, h = p.lcd_carrier
    y = p.baffle_back_y + 3.9
    c = Pos(p.lcd_x, y + p.pcb_t / 2, p.strip_zc) * Box(w, p.pcb_t, h)
    c = fillet(c.edges().filter_by(Axis.Y), 1.0)
    fpc = Pos(p.lcd_x + 20, y + p.pcb_t + 0.6, p.strip_zc) * Box(16, 1.2, 6)
    return cut_fasteners(c, "lcd_carrier", fs, p) + fpc


def battery_cells(p: Params):
    by, bz = p.battery_axis
    cells = []
    for i in (-1, 0, 1):
        c = Cylinder(p.cell_d / 2, p.cell_l)
        c = fillet(c.edges(), 1.0)
        cells.append(Pos(i * (p.cell_l + 1.0), by, bz) * Rot(0, 90, 0) * c)
    return Compound(children=cells)


def battery_nickel(p: Params):
    by, bz = p.battery_axis
    out = []
    for i in (-1.5, -0.5, 0.5, 1.5):
        x = i * (p.cell_l + 1.0)
        out.append(Pos(x, by, bz) * Rot(0, 90, 0) * Cylinder(7, 0.6 if abs(i) < 1 else 0.3))
    return Compound(children=out)


def battery_bms(p: Params):
    by, bz = p.battery_axis
    x = -(1.5 * (p.cell_l + 1.0) + 1.5)  # at the -X end, near the battery connector J3
    board = Pos(x, by, bz) * Box(1.6, 18, 18)
    lead = Pos(x - 0.8, by - 6, bz) * Box(2.5, 2, 8)
    return board + lead


def port_board(p: Params, fs):
    y0, y1 = port_board_y(p)
    top = p.usb_board_top
    b = Pos(0, (y0 + y1) / 2, top - 0.8) * Box(22, y1 - y0, 1.6)
    b = fillet(b.edges().filter_by(Axis.Z), 1.0)
    return cut_fasteners(b, "port_board", fs, p)


def usb_c(p: Params):
    # KiCad model: the opening is at -Y and the leads are at +Y. Turn it 180 degrees.
    u = vendor("kicad/USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal.step")
    return orient(u, (0, p.rear_y - 0.4 - 3.68, p.usb_board_top), (-1, 0, 0), (0, 0, 1))


# ---------------------------------------------------------------- the assembly

STEPS = [
    dict(n=1, title="Prepare the sleeve", groups=["shell"]),
    dict(n=2, title="Mount the drivers on the baffle", groups=["front"]),
    dict(n=3, title="Fit the keys and the LCD", groups=["front"]),
    dict(n=4, title="Fit the main PCB", groups=["front"]),
    dict(n=5, title="Fit the bay wall and the battery", groups=["front"]),
    dict(n=6, title="Build the rear panel", groups=["rear"]),
    dict(n=7, title="Install the front module", groups=["shell", "front"], move=dict(groups=["front"], by=(0, -200, 0))),
    dict(n=8, title="Install the rear panel", groups=["shell", "front", "rear"], move=dict(groups=["rear"], by=(0, 160, 0))),
    dict(n=9, title="Fit the covers and the knob", groups=["shell", "front", "rear", "covers"]),
]

COL = dict(
    shell="#ebe8e0", panel="#d8d4ca", strip="#c8c8c4", bay="#cfc6b4", grey="#b9b8b2", orange="#e2541f",
    rubber="#2a2a28", driver="#2f2f2d", pcb="#2d6a3e", chip="#8a8d91", blue="#2b5d9c", glass="#0d0d0f",
    brass="#c9a24a", screw="#2b2b2b", magnet="#b8bcc2", cell="#3d6fa8", nickel="#cfd3d6", acrylic="#1a1a1a",
)


def assembly(p: Params):
    """Return a list of part records. 'explode' is the move at full explode."""
    fs = fasteners(p)

    def P(name, label, shape, color, printed, process, explode, step, group, qty=1):
        return dict(name=name, label=label, shape=shape, color=COL.get(color, color), printed=printed,
                    process=process, explode=explode, step=step, group=group, qty=qty)

    parts = [
        P("sleeve", "Sleeve", sleeve(p, fs), "shell", True, "FDM or resin", (0, 0, 190), 1, "shell"),
        P("brace", "Brace", brace(p), "bay", True, "FDM", (0, 0, 250), 1, "shell"),
        P("feet", "Feet", feet(p), "rubber", True, "FDM (TPU)", (0, 0, -60), 1, "shell", 4),
        P("baffle", "Front baffle", baffle(p, fs), "panel", True, "FDM or resin", (0, -85, 0), 2, "front"),
        P("driver_l", "ND90-4 left", driver(p, -1), "driver", False, "Dayton Audio ND90-4", (0, -45, 0), 2, "front"),
        P("driver_r", "ND90-4 right", driver(p, 1), "driver", False, "Dayton Audio ND90-4", (0, -45, 0), 2, "front"),
        P("key_prev", "Key: prev", key(p, p.key_x[0]), "grey", True, "Resin", (0, -150, 0), 3, "front"),
        P("key_play", "Key: play", key(p, p.key_x[1]), "orange", True, "Resin, orange", (0, -150, 0), 3, "front"),
        P("key_next", "Key: next", key(p, p.key_x[2]), "grey", True, "Resin", (0, -150, 0), 3, "front"),
        P("lcd_panel", "LCD glass", lcd_panel(p), "glass", False, "2.4in TFT, ST7789 or ILI9341", (0, -65, 0), 3, "front"),
        P("lcd_backlight", "LCD backlight", lcd_backlight(p), "nickel", False, "Part of the LCD module", (0, -63, 0), 3, "front"),
        P("lcd_carrier", "LCD carrier PCB", lcd_carrier(p, fs), "blue", False, "Part of the LCD module", (0, -60, 0), 3, "front"),
        P("encoder_board", "Encoder board", enc_board(p, fs), "pcb", False, "2-layer PCB, 22 x 22 mm", (0, -60, 0), 3, "front"),
        P("encoder", "Encoder EC11E, 20 mm D-shaft", encoder(p), "nickel", False, "Alps EC11E15244G1 or equal", (0, -60, 0), 3, "front"),
        P("pcb_board", "Main PCB (KiCad)", kicad_pcb(p, "board"), "pcb", False, "4-layer PCB, 224 x 46 mm, pcb/bluespeaker.kicad_pcb", (0, -35, 0), 4, "front"),
        P("pcb_parts", "Main PCB parts (KiCad 3D)", kicad_pcb(p, "parts"), "chip", False, "71 parts, assembled by the PCB service", (0, -35, 0), 4, "front"),
        P("bay_wall", "Bay wall", bay_wall(p, fs), "bay", True, "FDM (PETG)", (0, 0, 70), 5, "front"),
        P("battery_cells", "3S 21700 cells", battery_cells(p), "cell", False, "3x Molicel P45B", (0, 0, -30), 5, "front"),
        P("battery_nickel", "Nickel strips", battery_nickel(p), "nickel", False, "Part of the pack", (0, 0, -30), 5, "front"),
        P("battery_bms", "Protection board", battery_bms(p), "pcb", False, "Part of the pack", (0, 0, -30), 5, "front"),
        P("rear_panel", "Rear panel", rear_panel(p, fs), "panel", True, "FDM or resin", (0, 125, 0), 6, "rear"),
        P("radiator_l", "ND90-PR left", radiator(p, -1), "driver", False, "Dayton Audio ND90-PR", (0, 70, 0), 6, "rear"),
        P("radiator_r", "ND90-PR right", radiator(p, 1), "driver", False, "Dayton Audio ND90-PR", (0, 70, 0), 6, "rear"),
        P("port_board", "USB-C port board", port_board(p, fs), "pcb", False, "2-layer PCB, STUSB4500", (0, 95, 0), 6, "rear"),
        P("usb_c", "USB-C receptacle", usb_c(p), "nickel", False, "GCT USB4105", (0, 95, 0), 6, "rear"),
        P("control_strip", "Control strip", control_strip(p), "strip", True, "FDM or resin, silver paint", (0, -125, 0), 9, "covers"),
        P("lcd_window", "LCD window", lcd_window(p), "acrylic", False, "1.5 mm smoked acrylic", (0, -175, 0), 9, "covers"),
        P("grille", "Front grille", grille(p), "#efede6", True, "Resin preferred", (0, -150, 0), 9, "covers"),
        P("knob", "Knob", knob(p), "grey", True, "Resin preferred", (0, -215, 0), 9, "covers"),
        P("knob_mark", "Knob mark", knob_mark(p), "orange", True, "Resin, orange", (0, -222, 0), 9, "covers"),
    ]

    # Fastener hardware, one record per joint group
    step_of = dict(baffle=7, bay=5, rear=8, driver=2, radiator=6, pcb=4, lcd=3, encoder=3, port=6)
    group_of = dict(baffle="front", bay="front", rear="rear", driver="front", radiator="rear", pcb="front", lcd="front",
                    encoder="front", port="rear")
    explode_of = dict(baffle=(0, -110, 0), bay=(0, -100, 0), rear=(0, 150, 0), driver=(0, -20, 0),
                      radiator=(0, 45, 0), pcb=(0, -20, 0), lcd=(0, -45, 0), encoder=(0, -40, 0), port=(0, 95, 25))
    insert_explode = dict(baffle=(0, 0, 190), bay=(0, 0, 70), rear=(0, 0, 190), driver=(0, -85, 0),
                          radiator=(0, 125, 0), pcb=(0, -85, 0))
    names = dict(baffle="baffle to sleeve", bay="baffle to bay wall", rear="rear panel to sleeve", driver="drivers",
                 radiator="radiators", pcb="main PCB", lcd="LCD module", encoder="encoder board", port="port board")
    for g in step_of:
        group = [f for f in fs if f.group == g]
        kind = group[0].kind
        size = {"csk3": "M3 x 10 countersunk", "pan3": f"M3 x {int(screw_len(group[0]))} pan head", "pan25": "M2.5 x 6 pan head, thread-forming"}[kind]
        parts.append(P(f"screws_{g}", f"Screws: {names[g]}", Compound(children=[screw_model(f) for f in group]), "screw",
                       False, size, explode_of[g], step_of[g], group_of[g], len(group)))
        if group[0].insert:
            # inserts are installed in step 1 (sleeve) or with the part that holds them
            host_step = {"baffle": 1, "rear": 1, "bay": 5, "driver": 2, "radiator": 6, "pcb": 2}[g]
            host_group = {"baffle": "shell", "rear": "shell"}.get(g, group_of[g])
            parts.append(P(f"inserts_{g}", f"Inserts: {names[g]}", Compound(children=[insert_model(f) for f in group]),
                           "brass", False, "M3 heat-set insert, 5.7 mm", insert_explode[g], host_step, host_group, len(group)))
    ms = magnets(p)
    parts.append(P("magnets", "Magnets 6 x 2 (baffle) and 6 x 1 (covers)",
                   Compound(children=[along(Cylinder(m.d / 2, m.t, align=MIN), m.at, m.dir) for m in ms]
                            + [along(Cylinder(m.d / 2, 1.0, align=MIN), m.at, (0, -1, 0)) for m in ms]),
                   "magnet", False, "N52 neodymium discs", (0, -120, 0), 9, "covers", 2 * len(ms)))
    return parts


# -------------------------------------------------------------------- outputs


def _qmul(a, b):
    """Hamilton product of two quaternions in glTF order (x, y, z, w)."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    ]


def fix_glb_root_transform(path: Path):
    """Correct the root-node transforms that export_gltf writes.

    The correct root transform is C * L: the shape location L, then the
    Z-up to Y-up conversion C (-90 degrees about X). export_gltf writes the
    translation of L without C, and it writes the rotation as R_L * C, not
    C * R_L. A part with a location therefore moves to the wrong place. If
    the location turns about an axis other than X, the part also turns the
    wrong way. Child nodes are in the converted frame and are correct.
    """
    c = [-math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5)]
    c_inv = [-c[0], 0.0, 0.0, c[3]]
    data = path.read_bytes()
    json_len = struct.unpack_from("<I", data, 12)[0]
    doc = json.loads(data[20 : 20 + json_len])
    rest = data[20 + json_len :]
    for scene in doc.get("scenes", []):
        for i in scene.get("nodes", []):
            node = doc["nodes"][i]
            t = node.get("translation")
            if t:
                x, y, z = t
                node["translation"] = [x, z, -y]
            q = node.get("rotation")
            if q:
                r_l = _qmul(q, c_inv)  # remove the conversion on the right
                node["rotation"] = _qmul(c, r_l)  # put it on the left
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<I4s", len(js), b"JSON") + js + rest
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)


# Print orientation of each printed part: rotation (X, Y, Z degrees) from the assembly pose.
# Rot(90, 0, 0) puts the front face (-Y) on the bed. Rot(-90, 0, 0) puts the rear face (+Y) on the bed.
PRINT_ROT = {
    "sleeve": (90, 0, 0),  # front opening down
    "brace": (0, 0, 0),
    "feet": (0, 0, 0),
    "baffle": (90, 0, 0),  # front face down
    "rear_panel": (-90, 0, 0),  # outer face down
    "bay_wall": (-90, 0, 0),  # rear face of the wall down
    "grille": (90, 0, 0),  # front face down
    "control_strip": (90, 0, 0),  # front face down
    "key_prev": (-90, 0, 0),  # cap up
    "key_play": (-90, 0, 0),
    "key_next": (-90, 0, 0),
    "knob": (-90, 0, 0),  # front face up
    "knob_mark": (90, 0, 0),  # flat
}


def on_bed(shape, rot=(0, 0, 0)):
    """Turn a part to its print orientation, centre it on X and Y, and put its lowest point at Z = 0."""
    s = Rot(*rot) * shape
    bb = s.bounding_box()
    return Pos(-(bb.min.X + bb.max.X) / 2, -(bb.min.Y + bb.max.Y) / 2, -bb.min.Z) * s


def export_stls(parts, stl_dir: Path, print_rot):
    stl_dir.mkdir(parents=True, exist_ok=True)
    for part in parts:
        if part["printed"]:
            shape = on_bed(part["shape"], print_rot.get(part["name"], (0, 0, 0)))
            export_stl(shape, stl_dir / f"{part['name']}.stl", tolerance=0.02, angular_tolerance=0.1)
            bb = shape.bounding_box()
            print(f"  {part['name'] + '.stl':<22} on bed {bb.size.X:6.1f} x {bb.size.Y:6.1f} x {bb.size.Z:6.1f}")


def export(parts, out_dir: Path, stl_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    stl_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.glb"):
        old.unlink()
    manifest = {"steps": STEPS, "parts": []}
    for part in parts:
        glb = out_dir / f"{part['name']}.glb"
        export_gltf(part["shape"], glb, binary=True, linear_deflection=0.05, angular_deflection=0.2)
        fix_glb_root_transform(glb)
        bb = part["shape"].bounding_box()
        rec = {k: part[k] for k in ("name", "label", "color", "printed", "process", "explode", "step", "group", "qty")}
        rec["file"] = f"models/{glb.name}"
        rec["size"] = [round(bb.size.X, 1), round(bb.size.Y, 1), round(bb.size.Z, 1)]
        manifest["parts"].append(rec)
        print(f"  {part['name']:<18} {bb.size.X:6.1f} x {bb.size.Y:6.1f} x {bb.size.Z:6.1f}")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    export_stls(parts, stl_dir, PRINT_ROT)


# Contact that the design intends: pins in a PCB, thread-forming screws in pilot holes
EXPECTED = {
    frozenset(x) for x in [
        ("pcb_board", "pcb_parts"), ("encoder", "encoder_board"), ("port_board", "usb_c"),
        ("screws_lcd", "baffle"), ("screws_port", "rear_panel"), ("screws_encoder", "baffle"),
    ]
}


def check(parts, tol=0.5):
    """Print every pair of parts that overlap by more than tol mm^3."""
    hits = 0
    for a, b in itertools.combinations(parts, 2):
        if frozenset((a["name"], b["name"])) in EXPECTED:
            continue
        ba, bb = a["shape"].bounding_box(), b["shape"].bounding_box()
        amin, amax, bmin, bmax = (tuple(v) for v in (ba.min, ba.max, bb.min, bb.max))
        if any(amax[i] <= bmin[i] or bmax[i] <= amin[i] for i in range(3)):
            continue
        try:
            common = a["shape"] & b["shape"]
            v = common.volume if common is not None else 0.0
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {a['name']} x {b['name']}: {e}")
            continue
        if v > tol:
            hits += 1
            print(f"  OVERLAP {a['name']} x {b['name']}: {v:.1f} mm^3")
    print(f"{hits} overlaps")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", action="store_true", help="write GLB files, STL files, and manifest")
    ap.add_argument("--show", action="store_true", help="send the model to OCP CAD Viewer")
    ap.add_argument("--check", action="store_true", help="report parts that collide")
    ap.add_argument("--stl", action="store_true", help="write only the STL files, in print orientation")
    ap.add_argument("--port", type=int, default=3939)
    args = ap.parse_args()

    p = Params()
    parts = assembly(p)

    if args.check:
        check(parts)
    if args.export:
        export(parts, ROOT / "docs" / "models", ROOT / "cad" / "stl")
    elif args.stl:
        export_stls(parts, ROOT / "cad" / "stl", PRINT_ROT)
    if args.show:
        from ocp_vscode import set_port, show

        set_port(args.port)
        show(*[x["shape"] for x in parts], names=[x["name"] for x in parts], colors=[x["color"] for x in parts])


if __name__ == "__main__":
    main()
