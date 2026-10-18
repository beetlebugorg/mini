"""Bluespeaker Mini: a smaller version with the hardware from ../bluedeck.

Hardware: two Dayton Audio PC68-4 (2.5 in full range) and one ZK-502C
Bluetooth amplifier board (12-24 V DC in, volume control, AUX in).

Coordinates: X is width (left to right), Y is depth (front is -Y), Z is
height (the floor is Z = 0). All units are mm.

Usage:
    uv run cad/bluespeaker_mini.py --export   # write GLB, STL, and manifest
    uv run cad/bluespeaker_mini.py --show     # send to OCP CAD Viewer
    uv run cad/bluespeaker_mini.py --check    # report parts that collide
"""

import argparse
import itertools
import json
import math
import sys
from dataclasses import dataclass
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
    Locations,
    Mode,
    Plane,
    Polygon,
    PolarLocations,
    Pos,
    Rectangle,
    RectangleRounded,
    RegularPolygon,
    Rot,
    loft,
    Vector,
    export_gltf,
    export_stl,
    extrude,
    fillet,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mini_common import (  # noqa: E402
    Fastener,
    export_stls,
    on_bed,
    post_gusset,
    along,
    fix_glb_root_transform,
    merge,
    orient,
    put,
    vendor,
)

ROOT = Path(__file__).resolve().parent.parent
MIN = (Align.CENTER, Align.CENTER, Align.MIN)


@dataclass
class MParams:
    # Shell
    width: float = 166.0
    height: float = 108.0
    depth: float = 94.0
    wall: float = 3.0
    edge_r: float = 3.0
    grille_t: float = 1.5
    baffle_t: float = 4.0
    rear_t: float = 3.0
    strip_top: float = 33.0
    seam: float = 0.5
    fit: float = 0.3  # clearance on each side of a panel in the sleeve opening
    rim_chamfer: float = 0.6  # lead-in chamfer inside the front opening (takes the elephant foot)
    post_setback: float = 0.4  # front posts sit this much deeper (insert rings, support marks)
    insert_relief: float = 0.5  # chamfer at the insert holes in the posts

    # Grille. "lattice": two layers of single-line ribs, for FDM. "holes": round holes, for resin.
    grille_style: str = "lattice"
    rib_w: float = 0.5  # one extrusion line of the 0.5 mm nozzle (LulzBot TAZ Workhorse SE)
    rib_pitch: float = 3.0  # 2.5 mm openings, about 69 % open: the orange baffle shows through
    hole_d: float = 2.5
    hole_pitch: float = 3.8
    grille_side: float = 3.0
    grille_band: float = 6.0

    # Speakers: Dayton Audio PC68-4, rear-mounted on spacer frames
    spk_x: float = 37.0
    spk_z: float = 69.5
    spk_cut: float = 65.0
    spk_spacer: float = 3.0
    spk_frame: float = 70.0  # spacer frame, square with cut corners
    spk_chamfer: float = 10.0
    spk_holes: float = 26.09

    # Amplifier: ZK-502C (dimensions from ../bluedeck/config.scad)
    amp_x0: float = 6.8  # X of the left board edge
    amp_standoff: float = 8.0  # PCB bottom above the sleeve floor
    # The rails stop below the PCB. The volume control hole in the baffle sets the board height at the front.
    # If the rails are higher than the hole, the hole pushes the front edge down and the back edge lifts off.
    rail_drop: float = 0.5  # two layers
    # Tray tabs: the blocks at the front of the tray that hold the two tray inserts. The insert hole is
    # 4.0 mm. The tab keeps at least 3 mm of plastic (6 lines) around it, so the hot insert does not push the wall out.
    tab_out: float = 5.5  # screw axis outside the board edge
    tab_gap: float = 0.3  # board edge to the inner face of the tab
    tab_wall: float = 5.5  # screw axis to the outer face and to the top face (3.5 mm of plastic past the hole)
    tab_d: float = 9.0  # tab depth along the screw
    # Board posts: two posts on the tray under the rear mounting holes of the ZK-502C. A small self-tapping
    # screw (1.9 mm thread, 3.28 mm head, 7 mm long) goes down through each hole into its post and holds the rear edge.
    # Hole positions: X from the left board edge, Y from the front edge. The front holes (Y 4.88) have no posts.
    amp_holes: tuple = ((3.0, 60.77), (47.5, 60.77))  # Y measured; X estimated
    board_post_d: float = 6.5  # 2.5 mm wall around the tap hole, 5 lines
    tap_d: float = 1.5  # tap hole for the 1.9 mm thread (PLA): the thread cuts 0.2 mm deep each side
    tap_depth: float = 6.5  # below the PCB bottom: the screw goes 5.4 mm into the post, 1.1 mm spare
    amp_w: float = 50.5
    amp_l: float = 82.0
    pcb_t: float = 1.6
    pot_x: float = 38.2
    pot_z: float = 5.5
    # Volume control body: a block on the PCB top that sticks out past the front board edge.
    # It sits in a pocket in the baffle back, so the board edge comes up to the baffle.
    pot_body_w: float = 10.0  # width (X), measured
    pot_body_h: float = 11.45  # height (Z) above the PCB top, measured
    pot_proud: float = 2.0  # the body front is this far in front of the board edge, measured
    pot_pocket_d: float = 1.5  # body pocket depth. The board edge stops pot_proud - pot_pocket_d behind the baffle
    pot_wall: float = 1.0  # baffle wall between the body pocket and the nut recess
    nut_t: float = 2.0  # volume control nut: 11.5 mm hex, 2 mm thick
    pot_pocket_clear: float = 0.3  # clearance at each side and at the top of the pocket
    aux_x: float = 11.2
    aux_z: float = 2.5
    dc_x: float = 38.0
    dc_z: float = 6.5

    # Drilled holes. Holes that open to the bed (or lie horizontal) print as small pilot holes with
    # a 45 degree tip. No support can fill them, and the slicer walls make a solid ring around each
    # pilot. Drill each hole to its full size after the print.
    pilot_d: float = 1.6
    membrane: float = 0.25  # one layer that bridges a counterbore that opens to the bed

    # Snap catches on the grille and the strip (see snap_catch). Each catch is a beam between two posts. The beam
    # bridges 0.5 mm above the grille back, so it prints along its length and flexes in the grille
    # plane: the layers never take the bending load. A bump on the beam clicks behind a lip at the
    # mouth of a pocket in the baffle. The lip face is 45 degrees, so a pull releases the grille.
    # Print fit_test_snap_baffle.stl and fit_test_snap_grille.stl to tune snap_bump.
    snap_span: float = 10.0  # free beam length between the posts
    snap_beam: float = 0.5  # beam width: one line
    snap_h: float = 2.5  # height of the posts and the top of the beam, above the grille back (10 layers)
    snap_gap: float = 0.5  # gap below the beam (2 layers)
    snap_post: float = 2.0  # post length along the beam
    snap_w: float = 3.0  # post width across the beam
    snap_bump: float = 0.4  # bump height on the beam
    snap_clear: float = 0.15  # pocket clearance around the posts (this locates the grille)
    snap_preload: float = 0.05  # the bump presses on the lip by this much: it pulls the grille flat
    snap_depth: float = 3.0  # pocket depth in the baffle (1 mm floor)

    # Socket head cap screws (ISO 4762 M3): 5.5 mm head, 3 mm high
    cap_d: float = 5.5
    cap_h: float = 3.0
    cap_clear: float = 0.25  # counterbore and port radius - head radius (half of one 0.5 mm line)
    port_band: float = 1.5  # solid ring around each head port in the grille and the strip (3 lines)
    port_chamfer: float = 0.5  # 45 degree chamfer at the front edge of each port (2 layers)
    screw_inset: float = 0.5  # corner screws sit this much in from the post centre, toward the box centre

    # Print compensation. The Cura profiles Parts and Shell have the calibrated horizontal expansion
    # (0.095 mm) and hole horizontal expansion (0.17 mm), so those parts print true to the model.
    # The Grille profiles have no expansion: it would make each 0.5 mm rib wider or narrower than one
    # line. So the grille model carries the net expansion on its snap catches and its head ports.
    grille_xy_comp: float = 0.095  # added to the posts and the bumps of the grille snap catches
    grille_hole_comp: float = 0.075  # added to the radius of the grille ports (0.17 - 0.095)
    parts_xy: float = 0.095  # the Parts profile expansion: the strip snap beam is this much narrower on each side

    # Knob
    knob_d: float = 22.0
    knob_h: float = 12.0
    knob_gap: float = 0.8

    # Fasteners: M3 heat-set inserts, short (3 mm long, 4.0 mm hole)
    post: float = 8.0
    insert_hole: float = 4.0
    insert_depth: float = 4.5

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
    def board_front_y(self):
        """Front edge of the ZK-502C: the volume control body sits on the floor of its pocket in the baffle."""
        return self.baffle_back_y + max(0.0, self.pot_proud - self.pot_pocket_d)

    @property
    def rear_inner_y(self):
        return self.rear_y - self.rear_t

    @property
    def spk_mount_y(self):
        return self.baffle_back_y + self.spk_spacer

    @property
    def strip_zc(self):
        return (self.wall + self.strip_top) / 2

    @property
    def pcb_top(self):
        return self.wall + self.amp_standoff + self.pcb_t

    @property
    def pot(self):
        return self.amp_x0 + self.pot_x, self.pcb_top + self.pot_z

    @property
    def aux(self):
        return self.amp_x0 + self.aux_x, self.pcb_top + self.aux_z

    @property
    def dc(self):
        return self.amp_x0 + self.dc_x, self.pcb_top + self.dc_z

    @property
    def post_c(self):
        x = self.width / 2 - self.wall - self.post / 2
        return x, self.wall + self.post / 2, self.height - self.wall - self.post / 2

    @property
    def corner_screws(self):
        """(x, z) of the four corner screws (front and rear), each with its corner signs (sx, sz)."""
        px, pz0, pz1 = self.post_c
        i = self.screw_inset
        return [(sx * (px - i), pz + sz * -i, sx, sz) for sx in (-1, 1) for pz, sz in ((pz0, -1), (pz1, 1))]


# ------------------------------------------------------------------ fasteners

SCREW_LEN = {"front": 8, "tray": 8, "rear": 6, "speaker": 5, "board": 7}


def head_sink(p: MParams, f: Fastener):
    """Depth of the counterbore for a cap head.

    front: the head top is flush with the grille face, in a round port in the grille or the strip.
    tray: the head stops 0.75 mm in front of the baffle, in a pocket on the back of the strip.
    rear: no counterbore. The head sits on the rear panel.
    """
    return {"front": p.grille_t, "tray": p.baffle_t - 1.75}.get(f.group, 0.0)


def pilot_depth(p: MParams, f: Fastener):
    """(face offset, depth) of the insert pilot hole after the first part. None: print the insert hole."""
    # M3 x 8: the screw tip goes 5.5 mm (front) or 6.25 mm (tray) past the back of the baffle
    return {"front": (p.post_setback, 6.5), "tray": (0.0, p.tab_d)}.get(f.group)  # tray: through the tab


def fasteners(p: MParams):
    fs = []
    for x, z, _, _ in p.corner_screws:
        fs.append(Fastener("front", "cap3", (x, p.baffle_front_y, z), (0, 1, 0), p.baffle_t, ("baffle", "sleeve")))
        fs.append(Fastener("rear", "cap3", (x, p.rear_y, z), (0, -1, 0), p.rear_t, ("rear_panel", "sleeve")))
    for x in tray_tab_x(p):
        fs.append(Fastener("tray", "cap3", (x, p.baffle_front_y, tray_tab_z(p)), (0, 1, 0), p.baffle_t, ("baffle", "tray")))
    h = p.spk_holes
    for sx in (-1, 1):
        for i, j in itertools.product((-1, 1), (-1, 1)):
            at = (sx * p.spk_x + i * h, p.spk_mount_y + 0.6, p.spk_z + j * h)
            fs.append(Fastener("speaker", "pan3", at, (0, -1, 0), 0.6, ("baffle",)))
    for hx, hy in p.amp_holes:  # down through the PCB into the tray posts
        at = (p.amp_x0 + hx, p.board_front_y + hy, p.pcb_top)
        fs.append(Fastener("board", "tap2", at, (0, 0, -1), p.pcb_t, ("tray",), insert=False, clear_d=2.0))
    return fs


def screw_model(f: Fastener, p: MParams):
    L = SCREW_LEN[f.group]
    if f.kind == "tap2":  # small self-tapping screw: 1.9 mm thread, 3.28 mm pan head
        head = fillet((Pos(0, 0, -1.3) * Cylinder(1.64, 1.3, align=MIN)).edges().group_by(Axis.Z)[0], 0.4)
        return along(head + Cylinder(0.95, L, align=MIN), f.at, f.dir)
    shank = Cylinder(1.5, L, align=MIN)
    if f.kind == "cap3":
        sink = head_sink(p, f)
        head = Pos(0, 0, -p.cap_h) * Cylinder(p.cap_d / 2, p.cap_h, align=MIN)
        head = head - Pos(0, 0, -p.cap_h - 0.01) * extrude(RegularPolygon(1.25 / math.cos(math.pi / 6), 6), amount=1.6)
        shank = Pos(0, 0, sink) * shank
        head = Pos(0, 0, sink) * head
    else:
        head = Pos(0, 0, -2.0) * Cylinder(2.75, 2.0, align=MIN)
        head = fillet(head.edges().group_by(Axis.Z)[0], 0.6)
    return along(head + shank, f.at, f.dir)


def insert_model(f: Fastener, p: MParams):
    body = Cylinder(1.99, 3.0, align=MIN) - Cylinder(1.5, 3.1, align=MIN)
    face = (pilot_depth(p, f) or (0.0, 0))[0]
    at = Vector(*f.at) + Vector(*f.dir).normalized() * (f.through + face)
    return along(body, at, f.dir)


def pilot(p: MParams, depth):
    """Pilot hole along +Z with a 45 degree tip. The tip has no flat roof, so the slicer adds no support in the hole."""
    r = p.pilot_d / 2
    return Cylinder(r, depth, align=MIN) + Pos(0, 0, depth) * Cone(r, 0, r, align=MIN)


def pilot_mouth(p: MParams, r_mouth):
    r = p.pilot_d / 2
    return Pos(0, 0, -0.01) * Cone(r_mouth + 0.01, r, r_mouth + 0.01 - r, align=MIN)


def hole_tool(f: Fastener, p: MParams):
    """Solid that cuts the holes for one fastener (built along +Z from f.at, then placed).

    First part: a counterbore for the cap head (with a one-layer membrane at its floor) and the
    clearance hole. Second part: a pilot hole for the insert (drill 4.0 mm), or a printed insert hole.
    """
    sink = head_sink(p, f) if f.kind == "cap3" else 0.0
    parts = []
    if sink > 0:
        parts.append(Pos(0, 0, -0.01) * Cylinder(p.cap_d / 2 + p.cap_clear, sink + 0.01, align=MIN))
        start = sink + p.membrane
        parts.append(Pos(0, 0, start) * Cylinder(f.clear_d / 2, f.through - start + 0.01, align=MIN))
    else:
        parts.append(Cylinder(f.clear_d / 2, f.through + 0.01, align=MIN))
    pd = pilot_depth(p, f)
    if pd:
        face, depth = pd
        mouth = pilot_mouth(p, p.insert_hole / 2 + p.insert_relief)
        parts.append(Pos(0, 0, f.through + face) * (mouth + pilot(p, depth)))
    elif f.insert:
        parts.append(Pos(0, 0, f.through) * Cylinder(p.insert_hole / 2, p.insert_depth, align=MIN))
    elif f.kind == "tap2":  # self-tapping screw: tap hole, no insert
        parts.append(Pos(0, 0, f.through - 0.01) * Cylinder(p.tap_d / 2, p.tap_depth + 0.01, align=MIN))
    return along(merge(parts), f.at, f.dir)


def snaps(p: MParams):
    """(x, z, sz, group) of the snap catches: four on the grille and four on the strip.

    Grille: near the corners of the top and bottom bands, clear of the speaker holes and the head ports.
    Strip: clear of the volume control, the AUX socket, the tray screw heads, and the head ports.
    sz: +1 or -1, the bump points to +Z or -Z, toward the nearer cover edge.
    """
    z_lo = p.strip_top + p.seam + p.grille_band / 2
    z_hi = p.height - p.wall - p.fit - p.grille_band / 2
    out = [(sx * 63.75, z, sz, "grille") for sx in (-1, 1) for z, sz in ((z_lo, -1), (z_hi, 1))]
    out += [(x, z, sz, "strip") for x, z, sz in ((-60.0, 24.0, 1), (-60.0, 9.0, -1), (62.0, 26.0, 1), (27.0, 7.0, -1))]
    return out


def snap_catch(p: MParams, comp=0.0, beam_comp=0.0):
    """One cover catch, built along +Z from the cover back. Local +Y is the bump side.

    comp: added to the posts and the bump face, for a profile with no horizontal expansion (grille).
    beam_comp: removed from each side of the beam, for a profile with expansion (strip), so the
    beam still prints as one line.
    """
    L, h, g = p.snap_span, p.snap_h, p.snap_gap
    t = p.snap_beam - 2 * beam_comp
    w2 = p.snap_w / 2
    posts = [Pos(sx * (L / 2 + p.snap_post / 2), 0, 0) * Box(p.snap_post + 2 * comp, p.snap_w + 2 * comp, h, align=MIN)
             for sx in (-1, 1)]
    beam = Pos(0, w2 - p.snap_beam / 2, g) * Box(L + p.snap_post, t, h - g, align=MIN)
    # bump profile across the beam: 45 degree catch face, short flat, 18 degree lead-in
    b = p.snap_bump + comp
    z0 = g + 0.1
    with BuildSketch(Plane.YZ) as sk:
        # the bump starts at the beam centre, so it joins a narrowed beam too
        yc = w2 - p.snap_beam / 2
        Polygon((yc, z0), (w2, z0), (w2 + b, z0 + b), (w2 + b, z0 + b + 0.25), (w2, h), (yc, h), align=None)
    bump = extrude(sk.sketch, amount=2.0, both=True)
    return merge([*posts, beam, bump])


def snap_pocket(p: MParams):
    """The pocket in the baffle for one catch, built along +Z from the baffle front. Local +Y is the bump side.

    The mouth is narrow and the pocket gets wider above the lip, so the pocket prints front face
    down with no support. Its floor is a 3.3 mm bridge.
    """
    L, c = p.snap_span, p.snap_clear
    w2 = p.snap_w / 2 + c
    lx = L + 2 * p.snap_post + 2 * c
    d = p.snap_depth
    main = Pos(0, 0, -0.01) * Box(lx, 2 * w2, d + 0.01, align=MIN)
    # 0.3 mm lead-in at the mouth: it takes the elephant foot of the first layer
    mouth = loft([Plane.XY.offset(-0.01) * Rectangle(lx + 0.6, 2 * w2 + 0.6), Plane.XY.offset(0.3) * Rectangle(lx, 2 * w2)])
    # the lip face: parallel to the bump catch face, moved in by the preload
    z0 = p.snap_gap + 0.1
    yb = p.snap_w / 2 - p.snap_preload  # where the lip face meets the beam face line
    zl = z0 + (w2 - yb)  # height where the lip face leaves the pocket wall
    top = yb + p.snap_bump + 0.15  # 0.1 mm clear of the bump top
    with BuildSketch(Plane.YZ) as sk:
        Polygon((w2 - 0.01, zl), (top, zl + top - w2), (top, d), (w2 - 0.01, d), align=None)
    groove = Pos(0, 0, 0) * extrude(sk.sketch, amount=2.5, both=True)
    return merge([main, mouth, groove])


def place_snap(shape, p: MParams, x, z, sz, y):
    """Place a snap part built along +Z (local +Y to the bump side) at (x, y, z), pointing into the baffle."""
    return orient(shape, (x, y, z), (-sz, 0, 0), (0, 1, 0))


def cover_snaps(p: MParams, group):
    """The catches of one cover, placed. Each cover gets the compensation of its own Cura profile."""
    catch = snap_catch(p, p.grille_xy_comp) if group == "grille" else snap_catch(p, beam_comp=p.parts_xy)
    return merge([place_snap(catch, p, x, z, sz, p.baffle_front_y) for x, z, sz, grp in snaps(p) if grp == group])


def snap_pockets(p: MParams):
    return [place_snap(snap_pocket(p), p, x, z, sz, p.baffle_front_y) for x, z, sz, _ in snaps(p)]


def cut_fasteners(shape, name, fs, p):
    for f in fs:
        if name in f.cut:
            shape = shape - hole_tool(f, p)
    return shape


def corner_cut(p: MParams, r, y0, depth, z_side):
    """Prism from y0 to y0 + depth: the corner of the panel, cut back to radius r around each corner screw.

    The cut is a square corner notch with its inner corner rounded to r, centred on the screw.
    z_side: -1 for the lower corners, +1 for the upper corners.
    """
    with BuildSketch(Plane.XZ) as sk:
        for x, z, sx, sz in p.corner_screws:
            if sz == z_side:
                with Locations((x, z)):
                    Circle(r)
                with Locations((x + sx * 5, z)):
                    Rectangle(10, 2 * r)
                with Locations((x, z + sz * 5)):
                    Rectangle(2 * r, 10)
                with Locations((x + sx * 5, z + sz * 5)):
                    Rectangle(10, 10)
    return put(extrude(sk.sketch, amount=depth), ymin=y0)


def port_r(p: MParams):
    """Radius of the head ports in the grille and the strip, and of the front counterbores in the baffle."""
    return p.cap_d / 2 + p.cap_clear


def head_ports(p: MParams, z_side, comp=0.0):
    """Round ports through a cover (grille_t thick) for the front cap heads, with a 45 degree chamfer at the face.

    The covers print front face down, so the chamfer is a 45 degree overhang that needs no support.
    z_side: -1 for the lower corners (strip), +1 for the upper corners (grille).
    """
    r = port_r(p) + comp
    c = p.port_chamfer
    tool = Pos(0, 0, -0.01) * Cylinder(r, p.grille_t + 0.02, align=MIN)
    tool = tool + Pos(0, 0, -0.01) * Cone(r + c + 0.01, r, c + 0.01, align=MIN)
    return merge([along(tool, (x, p.front_y, z), (0, 1, 0)) for x, z, _, sz in p.corner_screws if sz == z_side])


# ---------------------------------------------------------------- printed parts


def nut_recess(p: MParams):
    """Depth of the nut recess in the baffle front, and how far the nut stands in front of the baffle.

    The body pocket in the back and pot_wall use the baffle thickness first. The rest is the nut recess.
    The part of the nut that does not fit goes into a recess in the back of the control strip.
    """
    depth = min(p.nut_t, p.baffle_t - p.pot_pocket_d - p.pot_wall)
    return depth, p.nut_t - depth


def tray_tab_x(p: MParams):
    return p.amp_x0 - p.tab_out, p.amp_x0 + p.amp_w + p.tab_out


def tray_tab_z(p: MParams):
    return p.wall + p.amp_standoff + 2.0


def sleeve(p: MParams, fs):
    outer = RectangleRounded(p.width, p.height, p.edge_r)
    inner = RectangleRounded(p.inner_w, p.inner_h, 0.5)
    body = put(extrude(Plane.XZ * (outer - inner), amount=p.depth), x=0, ymin=p.front_y, zmin=0)
    px, pz0, pz1 = p.post_c
    s = p.post
    posts = []
    front0 = p.baffle_back_y + p.post_setback  # face of the front posts
    for x, z in [(-px, pz0), (px, pz0), (-px, pz1), (px, pz1)]:
        posts.append(Pos(x, (front0 + p.baffle_back_y + 10) / 2, z) * Box(s, p.baffle_back_y + 10 - front0, s))
        post = Pos(x, p.rear_inner_y - 5, z) * Box(s, 10, s)
        # 45 degree gusset from the wall corner, so the post prints without supports
        posts.append(post + post_gusset(x, z, s, p.rear_inner_y - 10, 1 if x > 0 else -1, -1 if z == pz0 else 1))
    body = body + merge(posts)
    for sx, sy in itertools.product((-1, 1), (-1, 1)):
        body = body - Pos(sx * 66, sy * 33, -0.01) * Cylinder(5.2, 1.0, align=MIN)
    # lead-in chamfer inside the front opening: it takes the elephant foot of the first layers
    c = p.rim_chamfer
    wide = Plane.XZ.offset(-(p.front_y - 0.01)) * RectangleRounded(p.inner_w + 2 * c, p.inner_h + 2 * c, 0.5 + c)
    narrow = Plane.XZ.offset(-(p.front_y + c)) * RectangleRounded(p.inner_w, p.inner_h, 0.5)
    body = body - put(loft([wide, narrow]), x=0, z=p.height / 2)
    # Front posts: pilot holes (drill 4.0 mm), so the supports under the post faces cannot fill them.
    # Rear posts: printed insert holes (they point up in the print).
    body = cut_fasteners(body, "sleeve", fs, p)
    # relief chamfers at the rear insert holes: the plastic that the hot insert pushes up goes here
    r = p.insert_hole / 2
    for x, z, _, _ in p.corner_screws:
        relief = Cone(r + p.insert_relief, r, p.insert_relief, align=MIN)
        body = body - along(relief, (x, p.rear_inner_y + 0.01, z), (0, -1, 0))
    return body


def spk_frame_sketch(p: MParams):
    a = p.spk_frame / 2
    c = p.spk_chamfer
    from build123d import Polygon

    return Polygon((-a + c, -a), (a - c, -a), (a, -a + c), (a, a - c), (a - c, a), (-a + c, a), (-a, a - c), (-a, -a + c))


def grille(p: MParams, style=None):
    """The grille. Its two upper corners have round ports that show the cap heads of the front screws."""
    style = style or p.grille_style
    g = grille_lattice(p) if style == "lattice" else grille_holes(p)
    # solid corner around each port, then the port
    z0, z1 = p.strip_top + p.seam, p.height - p.wall - p.fit
    with BuildSketch(Plane.XZ) as outline:
        RectangleRounded(p.panel_w, z1 - z0, 1.0)
    outline = put(extrude(outline.sketch, amount=p.grille_t), x=0, ymin=p.front_y, z=(z0 + z1) / 2)
    g = g + (corner_cut(p, port_r(p) + p.port_band, p.front_y, p.grille_t, 1) & outline)
    return g - head_ports(p, 1, p.grille_hole_comp)


def grille_lattice(p: MParams):
    """FDM grille: a solid border and two layers of ribs, each rib one extrusion line wide.

    Print it front face down. Layer 1 (the visible face) has horizontal ribs.
    Layer 2 has vertical ribs that bridge the 1.5 mm gaps. The slicer prints
    each rib as one straight line: no loops, no seams, no retractions.
    """
    z0, z1 = p.strip_top + p.seam, p.height - p.wall - p.fit
    h = z1 - z0
    win_w, win_h = p.panel_w - 2 * p.grille_side, h - 2 * p.grille_band
    half = p.grille_t / 2
    with BuildSketch(Plane.XZ) as frame:
        RectangleRounded(p.panel_w, h, 1.0)
        Rectangle(win_w, win_h, mode=Mode.SUBTRACT)
    nz = int(win_h // p.rib_pitch) + 1
    nx = int(win_w // p.rib_pitch) + 1
    with BuildSketch(Plane.XZ) as horiz:
        with GridLocations(1, p.rib_pitch, 1, nz):
            Rectangle(win_w + 1.0, p.rib_w)
    with BuildSketch(Plane.XZ) as vert:
        with GridLocations(p.rib_pitch, 1, nx, 1):
            Rectangle(p.rib_w, win_h + 1.0)
    g = put(extrude(frame.sketch, amount=p.grille_t), x=0, ymin=p.front_y, z=(z0 + z1) / 2)
    g = g + put(extrude(horiz.sketch, amount=half), x=0, ymin=p.front_y, z=(z0 + z1) / 2)
    g = g + put(extrude(vert.sketch, amount=half), x=0, ymin=p.front_y + half, z=(z0 + z1) / 2)
    return g + cover_snaps(p, "grille")


def grille_holes(p: MParams):
    z0, z1 = p.strip_top + p.seam, p.height - p.wall - p.fit
    h = z1 - z0
    nx = int((p.panel_w - 2 * p.grille_side - p.hole_d) // p.hole_pitch) + 1
    nz = int((h - 2 * p.grille_band - p.hole_d) // p.hole_pitch) + 1
    with BuildSketch(Plane.XZ) as sk:
        RectangleRounded(p.panel_w, h, 1.0)
        with GridLocations(p.hole_pitch, p.hole_pitch, nx, nz):
            Circle(p.hole_d / 2, mode=Mode.SUBTRACT)
    g = put(extrude(sk.sketch, amount=p.grille_t), x=0, ymin=p.front_y, z=(z0 + z1) / 2)
    return g + cover_snaps(p, "grille")


def grille_plate(p: MParams):
    """Slicer-infill grille, part 1: a solid plate with the head ports and the snap catches. See grille_window()."""
    z0, z1 = p.strip_top + p.seam, p.height - p.wall - p.fit
    with BuildSketch(Plane.XZ) as sk:
        RectangleRounded(p.panel_w, z1 - z0, 1.0)
    g = put(extrude(sk.sketch, amount=p.grille_t), x=0, ymin=p.front_y, z=(z0 + z1) / 2)
    g = g - head_ports(p, 1, p.grille_hole_comp)
    return g + cover_snaps(p, "grille")


def grille_window(p: MParams):
    """Slicer-infill grille, part 2: the window. In Cura it is a modifier mesh ("Modify settings for
    overlaps") with no walls and no skin, so the slicer infill makes the mesh. The window stops
    port_band from each head port, as on the lattice grille.
    """
    z0, z1 = p.strip_top + p.seam, p.height - p.wall - p.fit
    win_w, win_h = p.panel_w - 2 * p.grille_side, z1 - z0 - 2 * p.grille_band
    w = put(Box(win_w, p.grille_t, win_h), x=0, ymin=p.front_y, z=(z0 + z1) / 2)
    return w - corner_cut(p, port_r(p) + p.port_band, p.front_y - 0.01, p.grille_t + 0.02, 1)


def control_strip(p: MParams):
    h = p.strip_top - p.wall - p.fit
    zc = p.wall + p.fit + h / 2
    (kx, kz), (ax, az) = p.pot, p.aux
    with BuildSketch(Plane.XZ) as sk:
        RectangleRounded(p.panel_w, h, 1.0)
        with Locations((kx, kz - zc)):
            Circle(4.0, mode=Mode.SUBTRACT)  # pot bushing
        with Locations((ax, az - zc)):
            Circle(5.0, mode=Mode.SUBTRACT)  # AUX plug collar
    s = put(extrude(sk.sketch, amount=p.grille_t), x=0, ymin=p.front_y, zmin=p.wall + p.fit)
    # ports in the two lower corners show the cap heads of the front screws
    s = s - head_ports(p, -1)
    # recess on the back for the part of the pot nut that stands in front of the baffle
    _, nut_out = nut_recess(p)
    if nut_out > 0:
        s = s - along(Cylinder(7.0, nut_out + 0.2 + 0.01, align=MIN), (kx, p.baffle_front_y + 0.01, kz), (0, -1, 0))
    # pry slot at the top edge, centre: put a flat blade in it to lift the grille off its snap catches
    s = s - Pos(0, p.front_y + p.grille_t / 2, p.strip_top - 0.5) * Box(8.0, p.grille_t + 0.02, 1.0 + 0.02)
    # pockets on the back for the heads of the tray screws (they stop 0.75 mm in front of the baffle)
    for x in tray_tab_x(p):
        s = s - along(Cylinder(port_r(p) + 0.25, 1.0 + 0.01, align=MIN), (x, p.baffle_front_y + 0.01, tray_tab_z(p)), (0, -1, 0))
    return s + cover_snaps(p, "strip")


def baffle(p: MParams, fs):
    zc = p.height / 2
    (kx, kz), (ax, az) = p.pot, p.aux
    with BuildSketch(Plane.XZ) as sk:
        RectangleRounded(p.panel_w, p.panel_h, 1.0)
        with Locations((kx, kz - zc)):
            Circle(3.75, mode=Mode.SUBTRACT)  # pot bushing, 7 mm
        with Locations((ax, az - zc)):
            Circle(3.2, mode=Mode.SUBTRACT)  # AUX plug, 6.4 mm
    b = put(extrude(sk.sketch, amount=p.baffle_t), x=0, ymin=p.baffle_front_y, z=zc)
    # spacer frames for the speakers
    for sx in (-1, 1):
        frame = extrude(Plane.XZ * spk_frame_sketch(p), amount=p.spk_spacer)
        b = b + put(frame, x=sx * p.spk_x, ymin=p.baffle_back_y, z=p.spk_z)
    for sx in (-1, 1):
        c = (sx * p.spk_x, p.baffle_front_y - 0.01, p.spk_z)
        hole = Cylinder(p.spk_cut / 2, p.baffle_t + p.spk_spacer + 0.1, align=MIN)
        flare = Cone(p.spk_cut / 2 + 2, p.spk_cut / 2, 2, align=MIN)
        b = b - along(hole + flare, c, (0, 1, 0))
    # nut recess for the pot (11.5 mm hex nut): leaves pot_wall in front of the body pocket
    nut_d, _ = nut_recess(p)
    b = b - along(Cylinder(7.0, nut_d + 0.01, align=MIN), (kx, p.baffle_front_y - 0.01, kz), (0, 1, 0))
    # AUX: counterbore for the plug collar, leaves 1 mm of wall at the socket face
    b = b - along(Cylinder(5.0, p.baffle_t - 1.0, align=MIN), (ax, p.baffle_front_y - 0.01, az), (0, 1, 0))
    # one-layer membranes at the floor of the two recesses: each floor prints as one straight bridge.
    # Cut them out of the pot and AUX holes after the print.
    b = b + along(Cylinder(3.8, p.membrane, align=MIN), (kx, p.baffle_front_y + nut_d, kz), (0, 1, 0))
    b = b + along(Cylinder(3.3, p.membrane, align=MIN), (ax, p.baffle_front_y + p.baffle_t - 1.0, az), (0, 1, 0))
    # pocket in the back for the volume control body. The nut pulls the body onto the pocket floor.
    # It opens up in the print (front face down), so it needs no support.
    c = p.pot_pocket_clear
    depth = p.pot_pocket_d
    if depth > 0:
        pocket = Box(p.pot_body_w + 2 * c, depth + 0.01, p.pot_body_h + c + 0.25, align=(Align.CENTER, Align.MAX, Align.MIN))
        b = b - Pos(kx, p.baffle_back_y + 0.01, p.pcb_top - 0.25) * pocket
    b = cut_fasteners(b, "baffle", fs, p)
    # pockets for the snap catches of the grille and the strip
    for tool in snap_pockets(p):
        b = b - tool
    return b


def rear_panel(p: MParams, fs):
    zc = p.height / 2
    dx, dz = p.dc
    with BuildSketch(Plane.XZ) as sk:
        RectangleRounded(p.panel_w, p.panel_h, 1.0)
        with Locations((dx, dz - zc)):
            Circle(5.0, mode=Mode.SUBTRACT)  # DC plug
    r = put(extrude(sk.sketch, amount=p.rear_t), x=0, ymax=p.rear_y, z=zc)
    r = r - along(Cylinder(6.5, 1.5, align=MIN), (dx, p.rear_y + 0.01, dz), (0, -1, 0))  # plug collar
    return cut_fasteners(r, "rear_panel", fs, p)


def tray(p: MParams, fs):
    """Amplifier tray: floor plate, two rails under the board edges, tabs that screw to the baffle.

    No rear stop: the board slides 6 mm forward on the rails to put the bushing into the baffle.
    The nut on the volume control holds the front of the board. Two self-tapping screws hold the rear
    of the board to two posts. The rail tops are rail_drop below the PCB, so they cannot lift the
    front of the board. The board posts set the height at the rear.
    """
    y0 = p.baffle_back_y
    x0, x1 = p.amp_x0, p.amp_x0 + p.amp_w
    floor = p.wall
    top = p.wall + p.amp_standoff - p.rail_drop  # rail top, below the PCB bottom
    side = p.tab_out + p.tab_wall  # plate edge outside the board edge
    plate = Pos((x0 + x1) / 2, y0 + 42, floor) * Box(p.amp_w + 2 * side, 78, 2, align=MIN)
    rails = [Pos(x, y0 + 42, floor) * Box(3, 78, top - floor, align=MIN) for x in (x0 + 1.5, x1 - 1.5)]
    # tabs: from the board edge (plus tab_gap) out to tab_wall past the screw axis, tab_wall above the axis
    tab_w = p.tab_out - p.tab_gap + p.tab_wall
    tab_h = tray_tab_z(p) + p.tab_wall - floor
    tabs = [Pos(x0 - p.tab_gap - tab_w / 2, y0 + p.tab_d / 2, floor) * Box(tab_w, p.tab_d, tab_h, align=(Align.CENTER, Align.CENTER, Align.MIN)),
            Pos(x1 + p.tab_gap + tab_w / 2, y0 + p.tab_d / 2, floor) * Box(tab_w, p.tab_d, tab_h, align=(Align.CENTER, Align.CENTER, Align.MIN))]
    # posts under the rear mounting holes: the tops touch the PCB bottom (the rails stop rail_drop lower)
    posts = [Pos(x0 + hx, p.board_front_y + hy, floor) * Cylinder(p.board_post_d / 2, p.amp_standoff, align=(Align.CENTER, Align.CENTER, Align.MIN))
             for hx, hy in p.amp_holes]
    t = merge([plate, *rails, *tabs, *posts])
    return cut_fasteners(t, "tray", fs, p)


def knob(p: MParams):
    kx, kz = p.pot
    with BuildSketch(Plane.XZ) as sk:
        Circle(p.knob_d / 2)
        with PolarLocations(p.knob_d / 2, 40):
            Circle(0.7, mode=Mode.SUBTRACT)
    back = p.front_y - p.knob_gap
    k = put(extrude(sk.sketch, amount=p.knob_h), x=kx, ymax=back, z=kz)
    bore = Cylinder(3.05, 9.5, align=MIN)
    k = k - along(bore, (kx, back + 0.01, kz), (0, -1, 0))
    return k - knob_mark(p)


def knob_mark(p: MParams):
    kx, kz = p.pot
    y = p.front_y - p.knob_gap - p.knob_h + 0.6
    return Pos(kx, y, kz + 7.5) * Box(1.4, 1.2, 5.5)


def feet(p: MParams):
    return Compound(children=[Pos(sx * 66, sy * 33, -3) * Cylinder(5, 3.9, align=MIN)
                              for sx in (-1, 1) for sy in (-1, 1)])


# -------------------------------------------------------------- bought parts


def speaker(p: MParams, sx: int):
    """Dayton STEP: axis at X = Y = 34.03, front at -Z, plate front face at Z = -35.1, terminals at +Y."""
    s = vendor("dayton/pc68/PC68-4.stp")
    cx, cz = sx * p.spk_x, p.spk_z
    return orient(s, (cx - 34.03, p.spk_mount_y + 35.1, cz + 34.03), (1, 0, 0), (0, 1, 0))


def amp_board(p: MParams):
    """ZK-502C board. Local frame: X from the left edge, Y from the front edge, Z from the PCB top."""
    b = Box(p.amp_w, p.amp_l, p.pcb_t, align=(Align.MIN, Align.MIN, Align.MAX))
    return Pos(p.amp_x0, p.board_front_y, p.pcb_top) * b


def amp_parts(p: MParams):
    """Components of the ZK-502C, from the bluedeck mock-up. The positions are estimates from photos."""
    yc = 42.0  # board centre from the front edge (bluedeck uses the centre of an 84 mm board)
    parts = [
        Pos(p.pot_x, -p.pot_proud, 0) * Box(p.pot_body_w, 11, p.pot_body_h, align=(Align.CENTER, Align.MIN, Align.MIN)),  # volume control body
        Pos(p.aux_x, 6.5, 2.75) * Box(7, 13, 5.5),  # AUX socket
        Pos(18.5, 84 - 6.5, 6.5) * Box(25, 13, 13),  # speaker terminals (clear of the rear left mounting hole)
        Pos(p.dc_x, 84 - 7, 5.5) * Box(9, 14, 11),  # DC socket
        Pos(16, 84 - 30, 6.5) * Box(20, 12, 9),  # heat sink
    ]
    parts += [Pos(x + 5.5, yc + y + 5.5, 3.5) * Box(11, 11, 7) for x, y in [(5, -12), (18, -12), (5, 0), (32, 4)]]
    parts += [Pos(x, yc + y, 0) * Cylinder(4, 11, align=MIN) for x, y in [(38, -8), (10, -24)]]
    pot_axis = Plane(origin=(p.pot_x, -p.pot_proud, p.pot_z), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    parts.append(pot_axis * Cylinder(3.5, 7, align=MIN))  # threaded bushing
    parts.append(pot_axis * Cylinder(3.0, 16, align=MIN))  # shaft
    aux_axis = Plane(origin=(p.aux_x, 0, p.aux_z), x_dir=(1, 0, 0), z_dir=(0, -1, 0))
    parts.append(aux_axis * Cylinder(2.75, 0.01 + 0.5, align=MIN))
    return Pos(p.amp_x0, p.board_front_y, p.pcb_top) * Compound(children=parts)


def pot_nut(p: MParams):
    kx, kz = p.pot
    nut = extrude(Plane.XZ * RegularPolygon(11.5 / 2, 6), amount=p.nut_t) - along(Cylinder(3.5, 3, align=MIN), (0, -0.5, 0), (0, 1, 0))
    return put(nut, x=kx, ymax=p.baffle_front_y + nut_recess(p)[0], z=kz)


# ---------------------------------------------------------------- the assembly

STEPS = [
    dict(n=1, title="Prepare the sleeve", groups=["shell"]),
    dict(n=2, title="Mount the speakers on the baffle", groups=["front"]),
    dict(n=3, title="Fit the tray and the amplifier", groups=["front"]),
    dict(n=4, title="Install the front module", groups=["shell", "front"], move=dict(groups=["front"], by=(0, -140, 0))),
    dict(n=5, title="Install the rear panel", groups=["shell", "front", "rear"], move=dict(groups=["rear"], by=(0, 90, 0))),
    dict(n=6, title="Fit the covers and the knob", groups=["shell", "front", "rear", "covers"]),
]

COL = dict(grey="#8b8e91", orange="#e2541f", white="#f2f1ec",  # the three filaments
           driver="#2f2f2d", pcb="#1c1c1c", chip="#55575a", brass="#c9a24a", screw="#2b2b2b",
           nut="#9a9a9a")


def assembly(p: MParams):
    fs = fasteners(p)

    def P(name, label, shape, color, printed, process, explode, step, group, qty=1):
        return dict(name=name, label=label, shape=shape, color=COL.get(color, color), printed=printed,
                    process=process, explode=explode, step=step, group=group, qty=qty)

    parts = [
        P("sleeve", "Sleeve", sleeve(p, fs), "grey", True, "FDM, grey", (0, 0, 140), 1, "shell"),
        P("feet", "Feet", feet(p), "grey", True, "FDM, grey (or stick-on rubber feet)", (0, 0, -45), 1, "shell", 4),
        P("baffle", "Front baffle", baffle(p, fs), "orange", True, "FDM, orange (shows through the grille)", (0, -60, 0), 2, "front"),
        P("speaker_l", "PC68-4 left", speaker(p, -1), "driver", False, "Dayton Audio PC68-4", (0, -30, 0), 2, "front"),
        P("speaker_r", "PC68-4 right", speaker(p, 1), "driver", False, "Dayton Audio PC68-4", (0, -30, 0), 2, "front"),
        P("tray", "Amplifier tray", tray(p, fs), "grey", True, "FDM, grey", (0, 0, -40), 3, "front"),
        P("amp_board", "ZK-502C board", amp_board(p), "pcb", False, "ZK-502C Bluetooth amplifier", (0, 40, 20), 3, "front"),
        P("amp_parts", "ZK-502C parts", amp_parts(p), "chip", False, "Part of the ZK-502C", (0, 40, 20), 3, "front"),
        P("rear_panel", "Rear panel", rear_panel(p, fs), "grey", True, "FDM, grey", (0, 80, 0), 5, "rear"),
        P("pot_nut", "Volume control nut", pot_nut(p), "nut", False, "Supplied with the ZK-502C", (0, -70, 0), 6, "covers"),
        P("control_strip", "Control strip", control_strip(p), "white", True, "FDM, white", (0, -95, 0), 6, "covers"),
        P("grille", "Front grille (lattice)" if p.grille_style == "lattice" else "Front grille (holes)", grille(p), "grey", True,
          "FDM, grey, front face down, 0.4 mm nozzle" if p.grille_style == "lattice" else "Resin, grey",
          (0, -110, 0), 6, "covers"),
        P("knob", "Knob", knob(p), "orange", True, "FDM, orange", (0, -150, 0), 6, "covers"),
        P("knob_mark", "Knob mark", knob_mark(p), "white", True, "FDM, white", (0, -156, 0), 6, "covers"),
    ]
    info = dict(front=("baffle to sleeve", "M3 x 8 socket head cap screw", (0, -90, 0), 4, "front"),
                tray=("tray to baffle", "M3 x 8 socket head cap screw", (0, -80, 0), 3, "front"),
                rear=("rear panel to sleeve", "M3 x 6 socket head cap screw", (0, 110, 0), 5, "rear"),
                speaker=("speakers", "M3 x 5 pan head", (0, -12, 0), 2, "front"),
                board=("board to tray", "Self-tapping screw, 1.9 x 7, pan head 3.28 (your board screws)", (0, 0, 30), 3, "front"))
    insert_host = dict(front=(1, "shell", (0, 0, 140)), rear=(1, "shell", (0, 0, 140)),
                       tray=(3, "front", (0, 0, -40)), speaker=(2, "front", (0, -60, 0)))
    for g, (label, size, ex, step, group) in info.items():
        sel = [f for f in fs if f.group == g]
        parts.append(P(f"screws_{g}", f"Screws: {label}", Compound(children=[screw_model(f, p) for f in sel]), "screw",
                       False, size, ex, step, group, len(sel)))
        if g not in insert_host:  # self-tapping screws: no inserts
            continue
        hs, hg, hx = insert_host[g]
        parts.append(P(f"inserts_{g}", f"Inserts: {label}", Compound(children=[insert_model(f, p) for f in sel]), "brass",
                       False, "M3 heat-set insert, short (3 mm)", hx, hs, hg, len(sel)))
    return parts


# -------------------------------------------------------------------- outputs

# The snap catches press on the pocket lips on purpose (preload). The screws and the inserts
# pass through the pilot holes and the membranes, which you drill out after the print.
EXPECTED = {frozenset(x) for x in [("amp_board", "amp_parts"), ("baffle", "grille"), ("baffle", "control_strip"),
                                   ("sleeve", "screws_front"), ("sleeve", "inserts_front"), ("baffle", "screws_front"),
                                   ("baffle", "screws_tray"), ("tray", "screws_tray"), ("tray", "inserts_tray"),
                                   ("amp_board", "screws_board"), ("tray", "screws_board")]}


# Print orientation of each printed part (see PRINT_ROT in bluespeaker.py)
PRINT_ROT = {
    "sleeve": (90, 0, 0),  # front opening down
    "feet": (0, 0, 0),
    "baffle": (90, 0, 0),  # front face down, spacer frames up
    "rear_panel": (-90, 0, 0),  # outer face down
    "tray": (0, 0, 0),  # flat
    "grille": (90, 0, 0),  # front face down, snap catches up
    "control_strip": (90, 0, 0),  # front face down, snap catches up
    "knob": (-90, 0, 0),  # front face up
    "knob_mark": (90, 0, 0),  # flat
}


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
        rec["file"] = f"{out_dir.name}/{glb.name}"
        rec["edges"] = part["name"] != "grille"
        rec["size"] = [round(bb.size.X, 1), round(bb.size.Y, 1), round(bb.size.Z, 1)]
        manifest["parts"].append(rec)
        print(f"  {part['name']:<18} {bb.size.X:6.1f} x {bb.size.Y:6.1f} x {bb.size.Z:6.1f}")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    write_stls(parts, stl_dir)


def fit_test_snap(p: MParams):
    """Small coupons to test the snap catches: one baffle coupon with two pockets, one grille coupon,
    and one strip coupon. Print each with the Cura profile of its real part (Parts, Grille, Parts).
    Press each cover coupon into a pocket, then pull it out.
    """
    lx = p.snap_span + 2 * p.snap_post + 6
    block = Box(lx, 20, p.baffle_t, align=MIN) - Pos(0, -5, 0) * snap_pocket(p) - Pos(0, 5, 0) * snap_pocket(p)

    def cover(catch):
        return Pos(0, 0, p.grille_t) * (Pos(0, 0.5, -p.grille_t) * Box(lx, 8, p.grille_t, align=MIN) + catch)

    return block, cover(snap_catch(p, p.grille_xy_comp)), cover(snap_catch(p, beam_comp=p.parts_xy))


# Infill presets for the grille window (Cura settings on the modifier mesh). The line distance
# is 0.5 mm * 100 / density, times 2 for grid and times 3 for triangles and trihexagon.
# angles: one entry for each layer, then the list repeats. The grille has 6 layers of 0.25 mm.
# On the bed, 90 degrees runs along the grille width (horizontal ribs) and 0 runs along its height.
GRILLE_INFILL = [
    ("Lattice 3.0", "lines", 16.67, "[90,90,90,0,0,0]"),  # as the lattice grille: horizontal ribs on the face
    ("Lattice 2.0", "lines", 25.0, "[90,90,90,0,0,0]"),
    ("Diamond 3.0", "lines", 16.67, "[45,45,45,135,135,135]"),
    ("Grid 3.0", "grid", 33.33, "[]"),
    ("Triangles 4.0", "triangles", 37.5, "[]"),
    ("Trihexagon 4.0", "trihexagon", 37.5, "[]"),
]


# Cura per-model settings for the plate: always solid, whatever the infill in the print settings
PLATE_SETTINGS = {"infill_sparse_density": "100", "infill_pattern": "lines", "infill_angles": "[]",
                  "gradual_infill_steps": "0"}


WINDOW_SPEED = 20   # mm/s; the free infill lines on the bed pull loose at higher speed
WINDOW_FLOW = 110   # %; more plastic gives each line a wider bond to the bed


def window_settings(preset=None):
    """Cura per-model settings that make a mesh a window of pure infill.

    preset=None: the window takes the infill density, pattern, and directions from the print
    settings, so the infill selector in Cura changes it. Else (pattern, density, angles).
    """
    s = {
        "infill_mesh": "True", "infill_mesh_order": "1",
        "wall_thickness": "0", "wall_line_count": "0",
        "top_bottom_thickness": "0", "top_layers": "0", "bottom_layers": "0", "initial_bottom_layers": "0",
        "zig_zaggify_infill": "False", "infill_wipe_dist": "0",
        "speed_infill": str(WINDOW_SPEED), "infill_material_flow": str(WINDOW_FLOW),
    }
    if preset:
        pattern, density, angles = preset
        s.update({"infill_pattern": pattern, "infill_sparse_density": f"{density:g}", "infill_angles": angles,
                  "gradual_infill_steps": "0"})
    return s


def cura_value(v):
    """A per-model setting value for a Cura 3MF.

    Cura keeps a value from a 3MF as text. Text breaks its formulas: for example
    infill_line_width * 100 / infill_sparse_density fails for "100", and "False" counts as true.
    A value that starts with "=" becomes a formula, which gives a real number or bool.
    Text settings (patterns) and lists (angles) stay as text, as in Cura's own profiles.
    """
    v = str(v)
    if v.startswith("=") or v in ("True", "False"):
        return v if v.startswith("=") else "=" + v
    try:
        float(v)
        return "=" + v
    except ValueError:
        return v


def write_3mf(path: Path, objects, rot, centre=(140.0, 140.0)):
    """Write a 3MF that Cura opens with the objects in place and with their per-model settings.

    objects: (name, shape, settings, (dx, dy)). All shapes turn by rot and share one offset, so
    a modifier stays on its plate. dx, dy move one object pair on the bed (mm).
    """
    import zipfile
    from xml.sax.saxutils import escape

    turned = [(n, Rot(*rot) * s, st, d) for n, s, st, d in objects]
    boxes = [s.bounding_box() for _, s, _, _ in turned]
    z0 = min(b.min.Z for b in boxes)
    res, items = [], []
    for i, (name, s, settings, (dx, dy)) in enumerate(turned, start=1):
        verts, tris = s.tessellate(0.02, 0.1)
        meta = "".join(f'<metadata name="cura:{k}" preserve="true" type="xs:string">{escape(cura_value(v))}</metadata>'
                       for k, v in settings.items())
        vx = "".join(f'<vertex x="{v.X:.4f}" y="{v.Y:.4f}" z="{v.Z - z0:.4f}"/>' for v in verts)
        tx = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tris)
        res.append(f'<object id="{i}" name="{escape(name)}" type="model">'
                   f'{f"<metadatagroup>{meta}</metadatagroup>" if meta else ""}'
                   f'<mesh><vertices>{vx}</vertices><triangles>{tx}</triangles></mesh></object>')
        items.append(f'<item objectid="{i}" transform="1 0 0 0 1 0 0 0 1 {centre[0] + dx} {centre[1] + dy} 0"/>')
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
             'xmlns:cura="http://software.ultimaker.com/xml/cura/3mf/2015/10">'
             f'<resources>{"".join(res)}</resources><build>{"".join(items)}</build></model>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    types = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)


def write_grille_infill(p: MParams, out_dir: Path):
    """grille_infill.3mf: the full grille. The window follows the infill in the Cura print settings.
    grille_infill_coupon.3mf: one corner coupon, the same.
    grille_infill_presets.3mf: six corner coupons, each with its own preset from GRILLE_INFILL.
    """
    rot = PRINT_ROT["grille"]
    plate, window = grille_plate(p), grille_window(p)
    bb = plate.bounding_box()
    centre = Pos(-(bb.min.X + bb.max.X) / 2, -(bb.min.Y + bb.max.Y) / 2, -(bb.min.Z + bb.max.Z) / 2)
    plate, window = centre * plate, centre * window
    write_3mf(out_dir / "grille_infill.3mf",
              [("grille_plate", plate, PLATE_SETTINGS, (0, 0)), ("grille_window", window, window_settings(), (0, 0))], rot)
    # coupon: one upper corner of the grille (head port, border, one snap catch, and 40 x 25 mm of window)
    pb = plate.bounding_box()
    cut = Pos(pb.max.X - 30, 0, pb.max.Z - 20) * Box(60, 20, 40)
    cp, cw = plate & cut, window & cut
    cp, cw = Pos(-(pb.max.X - 30), 0, -(pb.max.Z - 20)) * cp, Pos(-(pb.max.X - 30), 0, -(pb.max.Z - 20)) * cw
    write_3mf(out_dir / "grille_infill_coupon.3mf",
              [("coupon plate", cp, PLATE_SETTINGS, (0, 0)), ("coupon window", cw, window_settings(), (0, 0))], rot)
    objs = []
    for i, (name, *preset) in enumerate(GRILLE_INFILL):
        d = ((i % 2) * 70 - 35, (i // 2) * 48 - 48)
        objs.append((f"coupon {i + 1} plate", cp, PLATE_SETTINGS, d))
        objs.append((f"coupon {i + 1} window ({name})", cw, window_settings(preset), d))
    write_3mf(out_dir / "grille_infill_presets.3mf", objs, rot)
    print("  grille_infill.3mf, grille_infill_coupon.3mf, grille_infill_presets.3mf (slicer-infill grille, for Cura)")


def write_stls(parts, stl_dir: Path):
    export_stls(parts, stl_dir, PRINT_ROT)
    p = MParams()
    for name, shape in zip(("baffle", "grille", "strip"), fit_test_snap(p)):
        export_stl(shape, stl_dir / f"fit_test_snap_{name}.stl", tolerance=0.01, angular_tolerance=0.1)
    print("  fit_test_snap_baffle.stl, fit_test_snap_grille.stl, fit_test_snap_strip.stl (snap catch fit test)")
    # the other grille style, for the other print process
    p = MParams()
    other = "holes" if p.grille_style == "lattice" else "lattice"
    export_stl(on_bed(grille(p, other), PRINT_ROT["grille"]), stl_dir / f"grille_{other}.stl", tolerance=0.02, angular_tolerance=0.1)
    print(f"  grille_{other}.stl (alternative, on bed)")
    write_grille_infill(p, stl_dir)


def check(parts, tol=0.5):
    hits = 0
    for a, b in itertools.combinations(parts, 2):
        if frozenset((a["name"], b["name"])) in EXPECTED:
            continue
        ba, bb = a["shape"].bounding_box(), b["shape"].bounding_box()
        amin, amax, bmin, bmax = (tuple(v) for v in (ba.min, ba.max, bb.min, bb.max))
        if any(amax[i] <= bmin[i] or bmax[i] <= amin[i] for i in range(3)):
            continue
        common = a["shape"] & b["shape"]
        v = common.volume if common is not None else 0.0
        if v > tol:
            hits += 1
            print(f"  OVERLAP {a['name']} x {b['name']}: {v:.1f} mm^3")
    print(f"{hits} overlaps")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--stl", action="store_true", help="write only the STL files, in print orientation")
    ap.add_argument("--port", type=int, default=3939)
    args = ap.parse_args()
    p = MParams()
    parts = assembly(p)
    if args.check:
        check(parts)
    if args.export:
        export(parts, ROOT / "docs" / "models-mini", ROOT / "cad" / "stl-mini")
    elif args.stl:
        write_stls(parts, ROOT / "cad" / "stl-mini")
    if args.show:
        from ocp_vscode import set_port, show

        set_port(args.port)
        show(*[x["shape"] for x in parts], names=[x["name"] for x in parts], colors=[x["color"] for x in parts])


if __name__ == "__main__":
    main()
