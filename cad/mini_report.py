#!/usr/bin/env python3
"""Bluespeaker Mini: data, render sets, and the engineering report.

    uv run cad/mini_report.py --step           # cad/step-mini/*.step (from a BREP cache of the parts)
    uv run cad/mini_drawings.py                # the A3 drawing sheets (docs/Bluespeaker-Mini-Drawings.pdf)
    uv run cad/mini_report.py                  # docs/report-mini/{data.json, glb/}
    uv run --with pillow cad/mini_report.py --render   # render new or changed views to docs/report-mini/img/
    uv run --with pymupdf cad/mini_report.py --pdf     # docs/Bluespeaker-Mini-Engineering-Report.pdf (with the sheets)

The parts come from a BREP cache in cad/.cache-mini/ while the model source is unchanged.
A render set is a folder of GLB files and a manifest that render.html reads.
"""

import argparse
import functools
import http.server
import json
import math
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

import hashlib

from build123d import Box, Plane, Pos, Rectangle, Vector, export_brep, export_gltf, export_step, import_brep

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bluespeaker_mini as m  # noqa: E402
from mini_common import fix_glb_root_transform, on_bed  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "report-mini"
PLA_DENSITY = 1.24  # g/cm3
CACHE = ROOT / "cad" / ".cache-mini"
STEP_DIR = ROOT / "cad" / "step-mini"


def load_parts(p):
    """The assembly parts. The shapes come from a BREP cache when the model source is unchanged."""
    key = hashlib.sha1(b"".join((ROOT / "cad" / f).read_bytes() for f in ("bluespeaker_mini.py", "bluespeaker.py"))).hexdigest()[:12]
    d = CACHE / key
    meta = d / "parts.json"
    if meta.exists():
        parts = json.loads(meta.read_text())
        for x in parts:
            x["shape"] = import_brep(str(d / f"{x['name']}.brep"))
        print("  parts from the cache", d.name)
        return parts
    parts = m.assembly(p)
    d.mkdir(parents=True, exist_ok=True)
    for x in parts:
        export_brep(x["shape"], str(d / f"{x['name']}.brep"))
    meta.write_text(json.dumps([{k: v for k, v in x.items() if k != "shape"} for x in parts]))
    for old in CACHE.iterdir():
        if old != d and old.is_dir():
            for f in old.iterdir():
                f.unlink()
            old.rmdir()
    print("  parts built and cached", d.name)
    return parts


def write_step(parts):
    """One STEP file for each part, in the assembly position (millimetres)."""
    STEP_DIR.mkdir(parents=True, exist_ok=True)
    for x in parts:
        export_step(x["shape"], str(STEP_DIR / f"{x['name']}.step"))
    (STEP_DIR / "parts.json").write_text(json.dumps([{k: v for k, v in x.items() if k != "shape"} for x in parts], indent=1))
    print("  wrote", STEP_DIR)

# ------------------------------------------------------------------ render sets


def write_set(name, items):
    """items: [(part name, shape, colour)]. Writes glb/<name>/*.glb and manifest.json."""
    d = OUT / "glb" / name
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.glb"):
        old.unlink()
    man = {"parts": []}
    for n, shape, col in items:
        if shape is None:
            continue
        f = d / f"{n}.glb"
        export_gltf(shape, f, binary=True, linear_deflection=0.02, angular_deflection=0.1)
        fix_glb_root_transform(f)
        man["parts"].append({"name": n, "color": col, "file": f"glb/{name}/{n}.glb", "explode": [0, 0, 0], "printed": True})
    (d / "manifest.json").write_text(json.dumps(man, indent=1))


def clip(shape, box_min, box_max):
    b = Pos(*[(a + c) / 2 for a, c in zip(box_min, box_max)]) * Box(*[c - a for a, c in zip(box_min, box_max)])
    try:
        r = shape & b
        return r if r is not None and r.volume > 0.001 else None
    except Exception:
        return None


def build():
    p = m.MParams()
    OUT.mkdir(parents=True, exist_ok=True)
    parts = load_parts(p)
    shapes = {x["name"]: x["shape"] for x in parts}
    colors = {x["name"]: x["color"] for x in parts}
    data = {"params": {k: getattr(p, k) for k in p.__dataclass_fields__}, "parts": [], "fasteners": []}

    # parts: size in print orientation, volume, mass at 100 % infill
    for x in parts:
        s = x["shape"]
        rec = {k: x[k] for k in ("name", "label", "process", "printed", "qty", "step")}
        rec["color"] = x["color"]
        if x["printed"]:
            bb = on_bed(s, m.PRINT_ROT.get(x["name"], (0, 0, 0))).bounding_box()
            rec["print_size"] = [round(bb.size.X, 1), round(bb.size.Y, 1), round(bb.size.Z, 1)]
            rec["volume_cm3"] = round(s.volume / 1000, 1)
            rec["mass_solid_g"] = round(s.volume / 1000 * PLA_DENSITY, 1)
        data["parts"].append(rec)

    for f in m.fasteners(p):
        data["fasteners"].append({"group": f.group, "kind": f.kind, "at": [round(v, 2) for v in f.at], "dir": list(f.dir),
                                  "through": f.through, "len": m.SCREW_LEN[f.group]})
    data["snaps"] = [{"x": x, "z": round(z, 2), "side": s_, "cover": g} for x, z, s_, g in m.snaps(p)]


    # render sets
    print("  render sets")
    allp = [(n, shapes[n], colors[n]) for n in shapes if n != "feet"]
    write_set("assembly", allp)
    sx, sz = 75.5, 100.5
    # 3D cut views: keep one side of the cut plane
    cut_sets = {
        "cut_corner": ((60, -60, 88), (85, -20, sz), ["sleeve", "baffle", "grille", "screws_front", "inserts_front"]),
        "cut_snap": ((56, -60, 96), (63.75, -30, 108), ["sleeve", "baffle", "grille"]),
        "cut_rear": ((sx, 20, 80), (85, 60, 110), ["sleeve", "rear_panel", "screws_rear", "inserts_rear"]),
        "cut_tray": ((50, -60, 0), (75, 0, m.tray_tab_z(p)), ["baffle", "control_strip", "tray", "screws_tray", "inserts_tray", "sleeve"]),
        "cut_pot": ((25, -70, 0), (70, 0, p.pot[1]), ["baffle", "control_strip", "knob", "pot_nut", "amp_parts", "amp_board", "tray", "sleeve"]),
    }
    for nm, (lo, hi, names) in cut_sets.items():
        write_set(nm, [(n, clip(shapes[n], lo, hi), colors[n]) for n in names])
    # single parts, in the assembly frame (close-ups) and in print orientation
    for n in ["grille", "control_strip", "baffle", "sleeve", "tray", "rear_panel", "knob"]:
        write_set(f"part_{n}", [(n, shapes[n], colors[n])])
    write_set("sleeve_inserts", [("sleeve", shapes["sleeve"], colors["sleeve"]), ("inserts_front", shapes["inserts_front"], colors["inserts_front"]),
                                 ("inserts_rear", shapes["inserts_rear"], colors["inserts_rear"])])
    write_set("baffle_hw", [(n, shapes[n], colors[n]) for n in ["baffle", "inserts_speaker", "screws_front", "screws_tray"]])
    for x in parts:
        if x["printed"]:
            s = on_bed(x["shape"], m.PRINT_ROT.get(x["name"], (0, 0, 0)))
            write_set(f"print_{x['name']}", [(x["name"], s, x["color"])])
    sb, sg, ss = m.fit_test_snap(p)
    write_set("coupons", [("fit_test_snap_baffle", Pos(0, 0, 0) * sb, colors["baffle"]),
                          ("fit_test_snap_grille", Pos(0, 30, 0) * sg, colors["grille"]),
                          ("fit_test_snap_strip", Pos(0, 45, 0) * ss, colors["control_strip"])])
    (OUT / "data.json").write_text(json.dumps(data, indent=1))
    print("  wrote", OUT)


# ------------------------------------------------------------------ renders

# name: (set, query). The view direction is in three.js axes: x right, y up, z toward the front.
SHOTS = {
    "hero": ("assembly", "zoom=0.78&dir=0.6,0.32,1&shadow=0.14", (2400, 1500)),
    "front": ("assembly", "ortho=1&dir=0,0,1&zoom=0.62&shadow=0", (2400, 1500)),
    "rear": ("assembly", "zoom=0.78&dir=-0.6,0.3,-1&shadow=0", (2400, 1500)),
    "top": ("assembly", "ortho=1&dir=0,1,0.0001&zoom=0.62&shadow=0", (2400, 1500)),
    "side": ("assembly", "ortho=1&dir=1,0,0&zoom=0.62&shadow=0", (2400, 1500)),
    "exploded": ("assembly", "explode=0.85&zoom=0.95&dir=0.8,0.4,1&shadow=0", (2400, 1500)),
    "corner_front": ("assembly", "target=75.5,-47,100.5&rad=12&dir=-0.35,0.25,1&shadow=0", (1600, 1200)),
    "corner_low": ("assembly", "target=-75.5,-47,7.5&rad=12&dir=0.35,-0.15,1&shadow=0", (1600, 1200)),
    "cut_corner": ("cut_corner", "target=75.5,-40,100.5&rad=17&dir=0.15,0.9,0.6&shadow=0", (1600, 1200)),
    "cut_snap": ("cut_snap", "target=63.75,-44,101.7&rad=8&dir=1,0.35,0.35&shadow=0", (1600, 1200)),
    "cut_rear": ("cut_rear", "target=75.5,38,98&rad=16&dir=-1,0.3,-0.2&shadow=0", (1600, 1200)),
    "cut_tray": ("cut_tray", "target=61.3,-40,13&rad=14&dir=0.2,0.9,0.6&shadow=0", (1600, 1200)),
    "cut_pot": ("cut_pot", "target=45,-45,18&rad=20&dir=0.3,0.9,0.7&shadow=0", (1600, 1200)),
    "grille_back": ("part_grille", "dir=0,0.25,-1&zoom=0.6&shadow=0", (2400, 1300)),
    "grille_snap": ("part_grille", "target=63.75,-44,101.7&rad=10&dir=0.45,0.6,-1&shadow=0", (1600, 1200)),
    "strip_back": ("part_control_strip", "dir=0,0.3,-1&zoom=0.6&shadow=0", (2400, 900)),
    "strip_snap": ("part_control_strip", "target=62,-44,26&rad=10&dir=0.45,0.6,-1&shadow=0", (1600, 1200)),
    "baffle_front": ("part_baffle", "ortho=1&dir=0,0,1&zoom=0.6&shadow=0", (2400, 1600)),
    "baffle_back": ("baffle_hw", "dir=0.3,0.3,-1&zoom=0.62&shadow=0", (2400, 1600)),
    "baffle_pocket": ("part_baffle", "target=63.75,-46,101.7&rad=10&dir=0.3,0.4,1&shadow=0", (1600, 1200)),
    "baffle_pot": ("part_baffle", "target=40,-46,17&rad=16&dir=0.2,0.3,1&shadow=0", (1600, 1200)),
    "sleeve_front": ("sleeve_inserts", "dir=0.35,0.3,1&zoom=0.72&shadow=0", (2400, 1600)),
    "sleeve_post": ("sleeve_inserts", "target=75.5,-38,100.5&rad=12&dir=-0.5,-0.3,1&shadow=0", (1600, 1200)),
    "sleeve_rear_post": ("sleeve_inserts", "target=75.5,38,100.5&rad=14&dir=-0.6,-0.4,-1&shadow=0", (1600, 1200)),
    "tray": ("part_tray", "dir=0.6,0.6,1&zoom=0.7&shadow=0", (1600, 1200)),
    "rear_panel": ("part_rear_panel", "dir=-0.3,0.25,-1&zoom=0.65&shadow=0", (2400, 1600)),
    "knob": ("part_knob", "dir=0.4,0.4,1&zoom=0.9&shadow=0", (1200, 1200)),
    "coupons": ("coupons", "dir=0.5,1.2,0.8&zoom=0.8&shadow=0", (1600, 1200)),
}
PRINT_SHOTS = ["sleeve", "baffle", "grille", "control_strip", "rear_panel", "tray", "knob", "knob_mark", "feet"]


def serve(directory, port=0):
    """Serve the directory on a free port (port 0). srv.server_address[1] gives the port."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    http.server.SimpleHTTPRequestHandler.log_message = lambda *a: None
    srv = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def render(only=None):
    img = OUT / "img"
    img.mkdir(exist_ok=True)
    srv = serve(OUT)
    port = srv.server_address[1]
    shots = dict(SHOTS)
    for n in PRINT_SHOTS:
        # print orientation: the GLB is Z-up in the model, so the bed is the three.js XZ plane
        shots[f"print_{n}"] = (f"print_{n}", "dir=0.55,0.75,1&zoom=0.75&shadow=0.12", (1600, 1200))
    jobs = []
    for name, (s, q, (w, h)) in shots.items():
        if only and name not in only:
            continue
        man = OUT / "glb" / s / "manifest.json"
        jpg = img / f"{name}.jpg"
        if not only and jpg.exists() and jpg.stat().st_mtime > man.stat().st_mtime:
            continue  # the render is newer than its model set
        url = f"http://127.0.0.1:{port}/render.html?m=glb/{s}/manifest.json&exp=0.9&{q}"
        cmd = ["chromium", "--headless=new", "--no-sandbox", "--enable-unsafe-swiftshader", "--use-angle=swiftshader",
               "--hide-scrollbars", f"--window-size={w},{h}", "--virtual-time-budget=60000", f"--screenshot={img / (name + '.png')}", url]
        jobs.append((name, subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)))
        if len(jobs) >= 6:
            n0, j0 = jobs.pop(0)
            j0.wait()
            print("  rendered", n0)
    for n0, j0 in jobs:
        j0.wait()
        print("  rendered", n0)
    srv.shutdown()


def trim():
    """Crop the white margin of each render and save it as JPEG."""
    from PIL import Image, ImageChops

    for f in sorted((OUT / "img").glob("*.png")):
        im = Image.open(f).convert("RGB")
        diff = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).convert("L").point(lambda v: 255 if v > 6 else 0)
        bb = diff.getbbox()
        if bb and not any(k in f.stem for k in ("corner_", "cut_", "_snap", "_pocket", "_post", "baffle_pot")):
            pad = 24
            im = im.crop((max(0, bb[0] - pad), max(0, bb[1] - pad), min(im.width, bb[2] + pad), min(im.height, bb[3] + pad)))
        im.save(f.with_suffix(".jpg"), quality=88)


def pdf():
    srv = serve(OUT)
    port = srv.server_address[1]
    out = ROOT / "docs" / "Bluespeaker-Mini-Engineering-Report.pdf"
    subprocess.run(["chromium", "--headless=new", "--no-sandbox", "--virtual-time-budget=30000", "--no-pdf-header-footer",
                    f"--print-to-pdf={out}", f"http://127.0.0.1:{port}/report.html"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    srv.shutdown()
    import pymupdf

    rep = pymupdf.open(out)
    rep.insert_pdf(pymupdf.open(ROOT / "docs" / "Bluespeaker-Mini-Drawings.pdf"))
    tmp = out.with_suffix(".tmp.pdf")
    rep.save(tmp, garbage=3, deflate=True)
    tmp.replace(out)
    print("  wrote", out, rep.page_count, "pages")


# ------------------------------------------------------------------ report page

PROFILES = [("Shell", "Bluespeaker_Mini_PLA_Shell"), ("Parts", "Bluespeaker_Mini_PLA_Parts"),
            ("Grille", "Bluespeaker_Mini_PLA_Grille"), ("Grille Infill", "Bluespeaker_Mini_PLA_Grille_Infill")]

# label, keys (first found wins), unit
PROFILE_ROWS = [
    ("Layer height", ["layer_height"], "mm"), ("First layer height", ["layer_height_0"], "mm"),
    ("Line width", ["line_width"], "mm"), ("Wall thickness", ["wall_thickness"], "mm"),
    ("Wall line count", ["wall_line_count"], ""), ("Top/bottom thickness", ["top_bottom_thickness"], "mm"),
    ("Infill", ["infill_sparse_density"], "%"), ("Infill pattern", ["infill_pattern"], ""),
    ("Printing temperature", ["material_print_temperature"], "°C"), ("First layer temperature", ["material_print_temperature_layer_0"], "°C"),
    ("Print speed", ["speed_print"], "mm/s"), ("Outer wall speed", ["speed_wall_0"], "mm/s"),
    ("Infill speed", ["speed_infill"], "mm/s"), ("First layer speed", ["speed_layer_0"], "mm/s"),
    ("Travel speed", ["speed_travel"], "mm/s"), ("Retraction", ["retraction_amount"], "mm"),
    ("Retraction speed", ["retraction_speed"], "mm/s"), ("Fan", ["cool_fan_speed", "cool_fan_speed_min"], "%"),
    ("Fan full at layer", ["cool_fan_full_layer"], ""), ("Bridge fan", ["bridge_fan_speed"], "%"),
    ("Minimum layer time", ["cool_min_layer_time"], "s"), ("Adhesion", ["adhesion_type"], ""),
    ("Brim lines", ["brim_line_count"], ""), ("Supports", ["support_enable"], ""), ("Support type", ["support_type"], ""),
    ("Horizontal expansion", ["xy_offset"], "mm"), ("Hole horizontal expansion", ["hole_xy_offset"], "mm"),
    ("Shrinkage XY", ["material_shrinkage_percentage_xy"], "%"), ("Shrinkage Z", ["material_shrinkage_percentage_z"], "%"),
    ("Bridge settings", ["bridge_settings_enabled"], ""), ("Outer wall wipe", ["wall_0_wipe_dist"], "mm"),
    ("Seam", ["z_seam_type"], ""), ("Extra skin wall count", ["skin_outline_count"], ""),
    ("Skin line directions", ["skin_angles"], ""), ("Monotonic top/bottom", ["skin_monotonic"], ""), ("Combing", ["retraction_combing"], ""),
]


def read_profile(stem):
    vals = {}
    for f in (ROOT / "cura" / f"{stem}.inst.cfg", ROOT / "cura" / f"{stem}_e0.inst.cfg"):
        sec = None
        for line in f.read_text().splitlines():
            if line.startswith("["):
                sec = line
            elif sec == "[values]" and "=" in line:
                k, v = (x.strip() for x in line.split("=", 1))
                vals[k] = v
            elif line.startswith("name ="):
                vals.setdefault("_name", line.split("=", 1)[1].strip())
    return vals


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def table(head, rows, cls=""):
    h = "".join(f"<th>{esc(x)}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>'


def fig(img, cap, cls=""):
    return f'<figure class="{cls}"><img src="{img}"><figcaption>{cap}</figcaption></figure>'


PART_INFO = {
    "sleeve": dict(orient="Front opening down", profile="Shell", supports="From the build plate, below the four front posts only",
                   faces="Front rim (first layer) is the visible front edge. Outside faces are visible.",
                   post="Remove the supports below the front posts. Drill the four front pilot holes Ø4.0 × 7. Install 8 inserts."),
    "baffle": dict(orient="Front face down", profile="Parts", supports="None. All roofs are bridges of 14 mm or less.",
                   faces="Front face (first layer) shows through the grille.",
                   post="Drill the six counterbore membranes Ø3.4 from the back. Cut the pot and AUX membranes. Install 8 inserts in the spacer frames."),
    "grille": dict(orient="Front face down, snap catches up", profile="Grille (or Grille Infill for the 3MF)", supports="None",
                   faces="Front face (first layer) is the visible face.", post="None. Check that the four catch beams are free of the plate below them."),
    "control_strip": dict(orient="Front face down, snap catches up", profile="Parts", supports="None",
                          faces="Front face (first layer) is the visible face.", post="Check that the four catch beams are free."),
    "rear_panel": dict(orient="Outer face down", profile="Parts", supports="None", faces="Outer face.", post="None"),
    "tray": dict(orient="Flat", profile="Parts", supports="None", faces="None visible.",
                 post="Drill the two tab pilot holes Ø4.0 through the tab. Install 2 inserts. Do not drill the two post tap holes."),
    "knob": dict(orient="Front face up", profile="Parts", supports="None", faces="Front face and the knurl.", post="Glue the knob mark into the groove."),
    "knob_mark": dict(orient="Flat", profile="Parts", supports="None", faces="Top face.", post="Glue into the knob groove."),
    "feet": dict(orient="Flat", profile="Parts", supports="None", faces="None visible.", post="Glue into the four recesses. Stick-on rubber feet are an option."),
}


def html():
    d = json.loads((OUT / "data.json").read_text())
    P = d["params"]
    profs = {n: read_profile(stem) for n, stem in PROFILES}
    parts = d["parts"]
    printed = [x for x in parts if x["printed"]]
    total_mass = sum(x["mass_solid_g"] * x["qty"] for x in printed)
    pages = []

    # ---- cover
    pages.append(f"""
<section class="page cover">
  <div class="brand"><span class="dot"></span>Bluespeaker</div>
  <p class="eyebrow">Engineering and manufacturing report</p>
  <h1>Bluespeaker Mini</h1>
  <p class="lede">This report gives the data that a manufacturer needs to print, finish, and assemble the Bluespeaker Mini.
  It contains the parts, the print settings, the joint sections, the fastener schedule, the fits, and the inspection steps.</p>
  <img class="hero" src="img/hero.jpg">
  {table(["Item", "Value"], [
      ["Revision", "0.3"], ["Date", "11 October 2026"],
      ["Source model", "<span class='mono'>cad/bluespeaker_mini.py</span> (build123d)"],
      ["Print files", "<span class='mono'>cad/stl-mini/</span>: STL in print orientation, 3MF for Cura"],
      ["Process", "FDM, PLA 2.85 mm, 0.5 mm nozzle (LulzBot TAZ Workhorse SE, Klipper)"],
      ["Units", "Millimetres. Angles in degrees. Ø is a diameter."],
      ["General tolerance", "±0.2 mm on printed parts unless a fit is given in section 8"]], "kv")}
</section>""")

    # ---- contents
    toc = ["Product overview", "Bill of materials", "Print instructions for each part", "Process settings (Cura)",
           "Engineering drawings (A3 sheets at the end)", "Fastener and insert schedule", "Snap-fit covers", "Fits and clearances",
           "Post-processing", "Assembly", "Inspection and acceptance", "Open items"]
    pages.append('<section class="page"><p class="eyebrow">Contents</p><h2>In this report</h2><ol class="toc">'
                 + "".join(f"<li><span>{i + 1}</span>{t}</li>" for i, t in enumerate(toc)) + "</ol>"
                 + '<div class="note" style="margin-top:0.3in"><b>Coordinates.</b> X is the width (+X to the right, seen from the front). '
                 'Y is the depth (−Y is the front face, at Y = −47). Z is the height (Z = 0 is the bottom of the sleeve). '
                 'The drawing sheets give their cut planes.</div></section>')

    # ---- 1 overview
    pages.append(f"""
<section class="page"><p class="eyebrow">1 · Product overview</p><h2>Overall views</h2>
  <div class="grid2">{fig("img/front.jpg", "Front. Overall 166 W × 108 H × 94 D. Drawing BSM-00.")}{fig("img/rear.jpg", "Rear. DC socket hole and four M3 × 6 screws.")}</div>
  {table(["Item", "Value"], [
      ["Outside size", "166 W × 108 H × 94 D, corner radius 3, wall 3"],
      ["Drivers", "2 × Dayton Audio PC68-4 (2.5 in, 4 Ω), rear-mounted on 3 mm spacer frames, 74 mm apart"],
      ["Amplifier", "ZK-502C Bluetooth board on a printed tray, 12–24 V DC"],
      ["Enclosure", "Sealed, about 1.1 L"],
      ["Front", "Grille (grey) and control strip (white), both snap onto the orange baffle. Four cap heads show in the corners."],
      ["Printed mass", f"About {total_mass:.0f} g if solid. The real mass is lower: the panels have 40 % infill."]], "kv")}
</section>""")
    pages.append(f"""
<section class="page"><p class="eyebrow">1 · Product overview</p><h2>Exploded view</h2>
  {fig("img/exploded.jpg", "From the back to the front: sleeve, rear panel, amplifier and tray, drivers, baffle, strip, grille, knob.", "wide")}
  <div class="grid2">{fig("img/corner_front.jpg", "Top-left corner: the cap head in its grille port.")}{fig("img/corner_low.jpg", "Bottom-right corner: the cap head in its strip port.")}</div>
</section>""")

    # ---- 2 BOM
    rows = []
    for i, x in enumerate(printed):
        info = PART_INFO.get(x["name"], {})
        rows.append([f"P{i + 1:02d}", esc(x["label"]), f'<span class="sw" style="background:{x["color"]}"></span>{esc(x["process"].split(",")[1].strip() if "," in x["process"] else x["process"])}',
                     str(x["qty"]), " × ".join(f"{v:g}" for v in x["print_size"]), f'{x["volume_cm3"]:g}', f'{x["mass_solid_g"]:g}',
                     info.get("profile", "Parts")])
    bought = [x for x in parts if not x["printed"]]
    brows = [[f"B{i + 1:02d}", esc(x["label"]), esc(x["process"]), str(x["qty"])] for i, x in enumerate(bought)]
    brows += [["B%02d" % (len(brows) + 1), "DC adapter", "12–24 V, 2 A or more. Check the plug size of the ZK-502C socket.", "1"],
              ["B%02d" % (len(brows) + 2), "Speaker wire", "2 × 0.5 mm², 150 mm", "2"],
              ["B%02d" % (len(brows) + 3), "Closed-cell foam tape", "3 × 6 mm, for the driver flanges and the panel seams", "0.6 m"]]
    pages.append(f"""
<section class="page"><p class="eyebrow">2 · Bill of materials</p><h2>Printed parts</h2>
  {table(["ID", "Part", "Colour", "Qty", "Print size X × Y × Z", "Volume cm³", "Mass solid g", "Profile"], rows)}
  <p class="small">Print size is in the print orientation, on the bed. The mass is for a solid part in PLA (1.24 g/cm³). The real mass depends on the infill.</p>
</section>""")
    pages.append(f"""
<section class="page"><p class="eyebrow">2 · Bill of materials</p><h2>Bought parts</h2>
  {table(["ID", "Part", "Specification", "Qty"], brows)}
</section>""")

    # ---- 3 per-part print sheets (two parts per page)
    sheet = []
    for x in printed:
        n = x["name"]
        info = PART_INFO.get(n, {})
        prof = info.get("profile", "Parts")
        kv = [["Orientation", info.get("orient", "")], ["Cura profile", f"Bluespeaker Mini - PLA {prof.split(' (')[0]} 0.25"],
              ["Supports", info.get("supports", "")], ["Size on the bed", " × ".join(f"{v:g}" for v in x["print_size"]) + " mm"],
              ["Visible faces", info.get("faces", "")], ["After the print", info.get("post", "")]]
        sheet.append(f'<div class="partsheet"><div class="ph">{fig(f"img/print_{n}.jpg", "")}</div><div><h3>{esc(x["label"])}'
                     f'<span class="tag">{x["qty"]} ×</span></h3>{table(["", ""], kv, "kv small")}</div></div>')
    for i in range(0, len(sheet), 3):
        pages.append(f'<section class="page"><p class="eyebrow">3 · Print instructions</p><h2>{"Each part on the bed" if i == 0 else "Each part on the bed (continued)"}</h2>{"".join(sheet[i:i + 3])}</section>')

    # ---- 4 profiles
    prow = []
    for label, keys, unit in PROFILE_ROWS:
        r = [label]
        for n, _ in PROFILES:
            v = next((profs[n][k] for k in keys if k in profs[n]), "—")
            r.append(esc(v) + (f" {unit}" if v != "—" and unit else ""))
        prow.append(r)
    pages.append(f"""
<section class="page"><p class="eyebrow">4 · Process settings</p><h2>Cura profiles</h2>
  <p class="lede small2">Cura 5.13, printer "LulzBot TAZ Workhorse | SE | 0.5 mm", PLA 2.85 mm, bed 60 °C. The profiles are in <span class="mono">cura/</span>.
  A dash means the printer default.</p>
  {table(["Setting"] + [n for n, _ in PROFILES], prow, "small dense")}
</section>""")
    pages.append(f"""
<section class="page"><p class="eyebrow">4 · Process settings</p><h2>Calibration and alignment</h2>
  {table(["Setting", "Value", "Profiles"], [["Shrinkage compensation XY", "100.21 %", "All"], ["Shrinkage compensation Z", "100 %", "All"],
        ["Printing temperature", "220 °C", "All"], ["Horizontal expansion", "0.095 mm", "Shell, Parts"], ["Hole horizontal expansion", "0.17 mm", "Shell, Parts"]])}
  <div class="note sp"><b>Grille compensation.</b> The Grille profiles have no horizontal expansion: it would change the width of each 0.5 mm rib.
  The model therefore adds 0.095 mm to the grille snap posts and bumps, and 0.075 mm to the radius of the grille head ports.
  The strip prints with the Parts profile, so its snap beam is modelled 0.31 mm wide: the 0.095 mm expansion on each side makes one 0.5 mm line.</div>
  <h3 class="sp">Layer and line alignment</h3>
  {table(["Feature", "Size", "Layers or lines"], [["Grille and strip", "1.5 mm", "6 layers"], ["Baffle", "4.0 mm", "16 layers"],
        ["Front counterbore", "1.5 mm", "6 layers"], ["Tray counterbore", "2.25 mm", "9 layers"], ["Membrane", "0.25 mm", "1 layer"],
        ["Snap catch height", "2.5 mm", "10 layers"], ["Gap below the snap beam", "0.5 mm", "2 layers"], ["Snap beam", "0.5 mm", "1 line"],
        ["Ring around a head port", "1.5 mm", "3 lines"], ["Head clearance", "0.25 mm", "½ line"], ["Grille rib", "0.5 mm", "1 line"],
        ["Grille rib pitch", "3.0 mm", "6 lines"]])}
  <p class="small">The grille, strip, and baffle print with a 0.25 mm first layer, so each height is on the layer grid. The sleeve keeps a 0.425 mm first layer for adhesion.</p>
  <h3 class="sp">Test coupons</h3>
  <div class="grid2">{fig("img/coupons.jpg", "Snap coupons: baffle (two pockets), grille catch, strip catch.")}
  <div>{table(["File", "Profile", "Test"], [["<span class='mono'>fit_test_snap_baffle.stl</span>", "Parts", "Two pockets"],
        ["<span class='mono'>fit_test_snap_grille.stl</span>", "Grille", "Grille catch"], ["<span class='mono'>fit_test_snap_strip.stl</span>", "Parts", "Strip catch"],
        ["<span class='mono'>grille_infill_presets.3mf</span>", "Grille Infill", "Six grille mesh presets"]])}
  <p class="small">Press each catch into a pocket until it clicks. Pull it out by hand. Accept: a clear click, the coupon sits flat, it comes out with no crack. Too tight: set <span class="mono">snap_bump</span> to 0.3. Too loose: set it to 0.5.</p></div></div>
</section>""")

    # ---- 5 drawings
    sheets = json.loads((ROOT / "docs" / "drawings-mini" / "sheets.json").read_text())
    srows = [[x["number"], esc(x["subject"]), x["scale"]] for x in sheets]
    pages.append(f"""
<section class="page"><p class="eyebrow">5 · Engineering drawings</p><h2>Drawing sheets</h2>
  <p class="lede small2">The A3 drawing sheets follow at the end of this report. They give the dimensions, the sections through each joint,
  and the notes for each part. Third-angle projection, millimetres, ±0.2 unless shown.</p>
  {table(["Sheet", "Subject", "Scale"], srows)}
  <div class="note sp"><b>Files.</b> STEP of each part in its assembly position: <span class="mono">cad/step-mini/</span>.
  FreeCAD document with the parts and a TechDraw page for each printed part: <span class="mono">cad/bluespeaker_mini.FCStd</span>.
  The sheets come from <span class="mono">cad/mini_drawings.py</span> (OpenCascade hidden-line views, the same algorithm as FreeCAD TechDraw).</div>
</section>""")
    pages.append(f"""
<section class="page"><p class="eyebrow">5 · Engineering drawings</p><h2>Joints in 3D</h2>
  <div class="grid2">{fig("img/cut_corner.jpg", "Front corner screw, cut at the screw axis (sheet BSM-08, section A-A).")}
  {fig("img/cut_snap.jpg", "Grille snap catch, cut at the beam centre (BSM-09, section B-B).")}
  {fig("img/cut_tray.jpg", "Tray screw, cut at the screw axis (BSM-08, section E-E).")}
  {fig("img/cut_rear.jpg", "Rear post with the 45° gussets (BSM-10, section G-G).")}
  {fig("img/cut_pot.jpg", "Volume control: nut recess, membrane, strip, knob (BSM-11, section J-J).")}
  {fig("img/corner_low.jpg", "Lower corner: cap head in its strip port.")}</div>
</section>""")

    # ---- 6 fasteners
    groups = {}
    for f in d["fasteners"]:
        groups.setdefault(f["group"], []).append(f)
    spec = {
        "front": ("Baffle to sleeve (front corners)", "M3 × 8 socket head cap, ISO 4762", "Short M3 insert in the sleeve front post", "Counterbore Ø6.0 × 1.5, membrane 0.25, clearance Ø3.4", "Pilot Ø1.6 → drill Ø4.0 × 7"),
        "tray": ("Tray to baffle", "M3 × 8 socket head cap, ISO 4762", "Short M3 insert in the tray tab", "Counterbore Ø6.0 × 2.25, membrane 0.25, clearance Ø3.4", "Pilot Ø1.6 → drill Ø4.0 through"),
        "rear": ("Rear panel to sleeve", "M3 × 6 socket head cap, ISO 4762", "Short M3 insert in the sleeve rear post", "Clearance Ø3.4, no counterbore", "Printed Ø4.0, 0.5 relief chamfer"),
        "speaker": ("Drivers to the spacer frames", "M3 × 5 pan head", "Short M3 insert in the spacer frame", "Driver flange hole", "Printed Ø4.0"),
        "board": ("ZK-502C rear edge to the tray posts", "Self-tapping, Ø1.9 × 7, pan head Ø3.28", "None: the screw cuts its thread", "Board mounting hole", "Printed tap hole Ø1.5 × 6.5"),
    }
    frows = [[spec[g][0], str(len(v)), spec[g][1], spec[g][2], spec[g][3], spec[g][4]] for g, v in groups.items()]
    lrows = [[f["group"], ", ".join(f"{a:g}" for a in f["at"]), ", ".join(f"{a:g}" for a in f["dir"]), (f'Ø1.9 × {f["len"]} self-tapping' if f["group"] == "board" else f'M3 × {f["len"]}')] for f in d["fasteners"]]
    pages.append(f"""
<section class="page"><p class="eyebrow">6 · Fastener and insert schedule</p><h2>Screws and inserts</h2>
  {table(["Joint", "Qty", "Screw", "Insert", "Hole in the first part", "Insert hole"], frows, "small")}
  <p class="small">Inserts: M3 heat-set, short (3 mm long, 4.0 mm hole), for example CNC Kitchen M3 Short. 18 in total. Install them with a soldering iron and an insert tip at the temperature that the insert supplier gives for PLA. Push the insert flush with the face. Do not push it below the face.</p>
  <div class="grid2">{fig("img/sleeve_post.jpg", "Sleeve front post: insert at the post face, 0.4 below the baffle back.")}{fig("img/sleeve_rear_post.jpg", "Sleeve rear post: 45° gussets to both walls, insert with relief chamfer.")}</div>
</section>""")
    pages.append(f"""
<section class="page"><p class="eyebrow">6 · Fastener and insert schedule</p><h2>Screw positions</h2>
  <p class="small">The entry point is where the screw enters the first part. The direction points into the material. Coordinates as in the contents page.</p>
  {table(["Joint", "Entry point X, Y, Z", "Direction", "Screw"], lrows, "small dense")}
</section>""")

    # ---- 7 snaps
    L, t, h, g = P["snap_span"], P["snap_beam"], P["snap_h"], P["snap_gap"]
    delta = P["snap_bump"] - P["snap_clear"]
    E = 3500.0
    I = (h - g) * t ** 3 / 12
    force = 192 * E * I * delta / L ** 3
    strain = 12 * t * delta / L ** 2 * 100
    mu = 0.3
    lead = math.atan(P["snap_bump"] / 1.25)
    f_in = force * (math.tan(lead) + mu) / (1 - mu * math.tan(lead))
    f_out = force * (1 + mu) / (1 - mu)
    srows = [[c["cover"], f'{c["x"]:g}', f'{c["z"]:g}', "+Z" if c["side"] > 0 else "−Z"] for c in d["snaps"]]
    pages.append(f"""
<section class="page"><p class="eyebrow">7 · Snap-fit covers</p><h2>How the catches work</h2>
  <div class="grid3">{fig("img/grille_snap.jpg", "Grille catch: two posts and one bridged beam with a bump.")}{fig("img/baffle_pocket.jpg", "Baffle pocket: narrow mouth (lip), wider inside, 1 mm floor.")}{fig("img/strip_snap.jpg", "Strip catch.")}</div>
  <ul class="clean">
    <li><b>Print direction.</b> The beam bridges 0.5 mm above the cover back, so the slicer prints it as straight lines along its length. It flexes in the cover plane. The bending load goes along the lines, not across the layers. An upright pin or hook would bend across the layers and crack.</li>
    <li><b>Lock.</b> The 0.4 mm bump clicks behind a 45° lip at the pocket mouth. The bump presses 0.05 mm on the lip, which pulls the cover flat and flush.</li>
    <li><b>Release.</b> A pull on the cover makes the 45° lip push the bump back. The catch releases and does not break.</li>
    <li><b>Location.</b> The posts fit their pockets with 0.15 mm clearance on each side. They locate the cover in X and Z.</li>
    <li><b>No support.</b> The baffle prints front face down. The pocket is narrow at the mouth and wider inside, so its walls only step back. The floor is a 3.3 mm bridge.</li>
  </ul>
  <div class="grid2 sp">{table(["Value (estimate, one catch)", ""], [
      ["Beam: length × width × height", f"{L:g} × {t:g} × {h - g:g} mm"], ["Deflection at the mouth", f"{delta:.2f} mm"],
      ["Bending strain (fixed–fixed beam, centre load)", f"{strain:.1f} %"], ["Spring force at full deflection", f"{force:.1f} N"],
      ["Push-on force (18° lead-in, μ 0.3)", f"{f_in:.1f} N"], ["Pull-off force (45° lip, μ 0.3)", f"{f_out:.1f} N"],
      ["Grille: four catches, pull-off", f"{4 * f_out:.0f} N"]], "kv small")}
  {table(["Cover", "X", "Z", "Bump"], srows, "small")}</div>
  <p class="small">PLA strain at yield along the lines is about 3 to 4 %. The estimate uses E = 3.5 GPa. Confirm with the test coupons (section 4).</p>
</section>""")
    pages.append(f"""
<section class="page"><p class="eyebrow">7 · Snap-fit covers</p><h2>Cover backs</h2>
  {fig("img/grille_back.jpg", "Grille back: four catches in the top and bottom bands, solid rings around the two head ports.", "wide")}
  {fig("img/strip_back.jpg", "Strip back: four catches, two pockets for the tray screw heads, the volume control and AUX holes, and the pry slot at the top edge.", "wide")}
  {fig("img/baffle_front.jpg", "Baffle front: eight snap pockets, six counterbores, the nut recess (Ø14 × 1.5), the AUX counterbore, and the two Ø65 cut-outs.", "wide")}
</section>""")

    # ---- 8 fits
    fits = [["Panels in the sleeve opening", "0.3 per side", "Baffle, grille, strip, rear panel"],
            ["Sleeve front lead-in chamfer", "0.6 × 45°", "Takes the elephant foot of the first layers"],
            ["Front post face setback", "0.4", "Insert rings and support marks cannot push the baffle forward"],
            ["Insert relief chamfer", "0.5 × 45°", "Takes the plastic that the hot insert pushes up"],
            ["Cap head in port and counterbore", "0.25 radial", "Ø6.0 for a Ø5.5 head. Grille ports +0.075 comp."],
            ["Head top to cover face", "0 (flush)", "Counterbore 1.5 + cover 1.5 = head 3.0"],
            ["Tray head pocket in the strip", "0.25 radial, 0.25 axial", "Head stands 0.75 in front of the baffle, pocket 1.0 deep"],
            ["Snap post in pocket", "0.15 per side", "Locates the covers"],
            ["Snap bump on the lip", "0.05 interference", "Preload"],
            ["Snap bump top to pocket wall", "0.1", "Groove clearance"],
            ["Knob to strip", "0.8", "Axial gap"],
            ["Strip to grille seam", "0.5", "Horizontal seam on the front"],
            ["Clearance holes", "Ø3.4", "M3 screws"],
            ["Insert holes", "Ø4.0", "Short M3 inserts"]]
    pages.append(f"""
<section class="page"><p class="eyebrow">8 · Fits and clearances</p><h2>Fits</h2>
  {table(["Fit", "Value (mm)", "Note"], fits)}
  <p class="small sp">All values are nominal model values. The Cura profiles compensate the calibrated shrink and expansion, so the printed parts follow the model.</p>
</section>""")

    # ---- 9 post-processing
    pages.append(f"""
<section class="page"><p class="eyebrow">9 · Post-processing</p><h2>Drill, cut, and insert</h2>
  {table(["Part", "Operation", "Tool", "Depth", "Note"], [
      ["Sleeve", "4 front post holes", "Drill Ø4.0", "7 mm", "The Ø1.6 pilot guides the drill"],
      ["Sleeve", "Remove the supports", "Pliers, scraper", "—", "Below the four front posts. Make the post faces flat."],
      ["Sleeve", "8 inserts", "Soldering iron, M3 insert tip", "Flush", "4 front, 4 rear"],
      ["Baffle", "6 counterbore membranes", "Drill Ø3.4", "Through", "From the back. The printed hole guides the drill."],
      ["Baffle", "Volume control membrane", "Knife", "—", "Cut out to the Ø7.5 hole, from the back"],
      ["Baffle", "AUX membrane", "Knife", "—", "Cut out to the Ø6.4 hole, from the back"],
      ["Baffle", "8 inserts", "Soldering iron", "Flush", "In the two spacer frames"],
      ["Tray", "2 tab holes", "Drill Ø4.0", "Through the tab", "Then 2 inserts"],
      ["Knob", "Knob mark", "Glue", "—", "White mark into the groove"],
      ["Grille, strip", "Check the catch beams", "Eye, fine blade", "—", "The 0.5 gap below each beam must be open. Cut any strings."]], "small")}
  <h3 class="sp">Membranes and pilot holes</h3>
  <p>A hole that opens to the bed fills with support, and a horizontal hole sags. The model therefore prints small holes as Ø1.6 pilot holes with a 45° tip, and it closes each counterbore with a 0.25 mm membrane. The slicer prints each membrane as one straight bridge. Drill or cut each one after the print.</p>
  <div class="grid2">{fig("img/baffle_back.jpg", "Baffle back with the speaker inserts and the screws.")}{fig("img/tray.jpg", "Tray: rails, two tabs with inserts, and two posts for the board screws.")}</div>
</section>""")

    # ---- 10 assembly
    pages.append(f"""
<section class="page"><p class="eyebrow">10 · Assembly</p><h2>Six steps</h2>
  <ol class="steps">
    <li><b>Prepare the sleeve.</b> Remove the supports below the four front posts. Drill the four front post holes Ø4.0 × 7. Install 8 inserts (4 front, 4 rear). Glue the four feet into the recesses on the bottom.</li>
    <li><b>Mount the speakers on the baffle.</b> Drill the membranes. Install 8 inserts in the spacer frames. Put foam tape on the driver flanges. Put each driver on its frame from the back, terminals down. Install four M3 × 5 pan head screws in each driver.</li>
    <li><b>Fit the tray and the amplifier.</b> Drill the tray tabs and install 2 inserts. Hold the tray against the baffle back. Install two M3 × 8 cap screws from the front. Remove the knob and the nut from the ZK-502C. Put the board on the rails, with the volume control and the AUX socket through the baffle. Install the nut in its recess. Install two self-tapping screws (Ø1.9 × 7) through the rear mounting holes into the posts. Stop when the head touches the board. Connect the speaker wires.</li>
    <li><b>Install the front module.</b> Push it into the sleeve front. Install four M3 × 8 cap screws through the baffle corners into the posts.</li>
    <li><b>Install the rear panel.</b> Align the DC socket with its hole. Install four M3 × 6 cap screws.</li>
    <li><b>Fit the covers and the knob.</b> Push the strip on until its four catches click. Push the grille on until its four catches click: the two upper heads go through the grille ports. Push the knob onto the shaft.</li>
  </ol>
  <div class="note sp"><b>To remove the covers.</b> Pull off the knob. Put a flat blade in the slot at the top edge of the strip, below the grille centre. Lift the bottom edge of the grille, then pull the grille off. Then lift the top edge of the strip and pull the strip off.</div>
  {fig("img/sleeve_front.jpg", "Sleeve from the front, with the eight inserts.", "mid")}
</section>""")

    # ---- 11 inspection
    pages.append(f"""
<section class="page"><p class="eyebrow">11 · Inspection and acceptance</p><h2>Checks</h2>
  {table(["Check", "Method", "Accept"], [
      ["Sleeve outside size", "Calliper", "166.0 × 108.0 × 94.0 ±0.3"],
      ["Sleeve front rim flat", "Put the rim on a flat plate", "No corner lifts more than 0.3"],
      ["Panel fit", "Push each panel into the sleeve opening", "Slides in by hand, no gap above 0.5 on a side"],
      ["Grille rib layers", "Cura layer view, then the part", "Layers 1–3: one line for each horizontal rib. Layers 4–6: one line for each vertical rib."],
      ["Head flush", "Straight edge across the port", "Head top within ±0.2 of the cover face"],
      ["Snap catches", "Coupons, then the covers", "Each catch clicks. The cover sits flat. Pull-off by hand with no crack."],
      ["Membranes", "Eye", "Each membrane is a closed flat bridge before you drill it"],
      ["Inserts", "Eye, then a screw", "Flush with the face, square, the screw turns in by hand"],
      ["Volume control", "Assemble", "The body sits on its pocket floor. The nut sits in its recess. The knob turns with 0.8 gap to the strip."],
      ["Air seal", "Play an 80–300 Hz sweep", "No rattle, no air noise at the seams"],
      ["Function", "Pair a phone, test AUX", "Sound from both drivers, AUX works"]])}
</section>""")

    # ---- 12 open items
    pages.append(f"""
<section class="page"><p class="eyebrow">12 · Open items</p><h2>Before production</h2>
  <ul class="clean">
    <li>The ZK-502C part positions in the model come from photos. Measure the real board and change <span class="mono">amp_parts()</span> and the port values in <span class="mono">MParams</span>.</li>
    <li>The volume control shaft is drawn round. Check whether the board has a knurled or a D-shaft, and change the knob bore to match.</li>
    <li>The snap forces in section 7 are estimates. Confirm them with the test coupons.</li>
    <li>The Orca profiles do not have the calibrated values yet. Use the Cura profiles.</li>
    <li>The drawing sheets give the main dimensions. For a size that a sheet does not show, measure the STEP file.</li>
    <li>The fit of a 3 mm short insert in a printed Ø4.0 hole depends on the insert brand. Test one insert in a coupon.</li>
  </ul>
  {fig("img/knob.jpg", "Knob: Ø22 × 12, 40 grip flutes, white mark.", "small-fig")}
</section>""")

    for i in range(len(pages)):
        if i:
            pages[i] = pages[i].replace("</section>", f'<div class="foot"><span>Bluespeaker Mini · Engineering report · Rev 0.3</span><span>{i + 1}</span></div></section>', 1)
    css = (OUT / "report.css").read_text()
    (OUT / "report.html").write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Bluespeaker Mini Engineering Report</title>'
                                     f'<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">'
                                     f'<style>{css}</style></head><body>{"".join(pages)}</body></html>')
    print("  wrote", OUT / "report.html", len(pages), "pages")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--render", nargs="*", help="render all shots, or the named shots")
    ap.add_argument("--html", action="store_true", help="write report.html from data.json")
    ap.add_argument("--step", action="store_true", help="write cad/step-mini/*.step")
    ap.add_argument("--pdf", action="store_true")
    a = ap.parse_args()
    if a.render is not None:
        render(set(a.render) or None)
        trim()
    elif a.step:
        write_step(load_parts(m.MParams()))
    elif a.html:
        html()
    elif a.pdf:
        html()
        pdf()
    else:
        build()


if __name__ == "__main__":
    main()
