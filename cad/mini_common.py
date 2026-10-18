"""Bluespeaker Mini: shared helpers for the model and the report.

Coordinates: X is width (left to right), Y is depth (front is -Y), Z is
height (the floor is Z = 0). All units are mm.
"""

import json
import math
import struct
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from build123d import Location, Plane, Pos, Rectangle, Rot, Vector, export_stl, import_step, loft

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "cad" / "vendor"


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
