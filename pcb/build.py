#!/usr/bin/env python3
"""Build the Bluespeaker main PCB project from netlist.py.

Writes:
    bluespeaker.kicad_sch   schematic with the real KiCad symbols and net labels
    bluespeaker.kicad_pcb   4-layer board with the footprints placed, nets assigned
    bluespeaker.kicad_pro, fp-lib-table, sym-lib-table

Run with the system Python, which has the KiCad pcbnew module:
    python3 pcb/build.py
"""

import json
import math
import re
import sys
import uuid
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from netlist import BOARD, PARTS, POWER_FLAGS  # noqa: E402

LIB = HERE / "lib"
NAME = "bluespeaker"


def uid():
    return str(uuid.uuid4())


# ------------------------------------------------------------------ s-expressions


def tokenize(text):
    return re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+', text)


def parse(text):
    stack, cur = [], []
    for t in tokenize(text):
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            done = cur
            cur = stack.pop()
            cur.append(done)
        else:
            cur.append(t)
    return cur


def dump(node, indent=0):
    if not isinstance(node, list):
        return node
    if all(not isinstance(x, list) for x in node):
        return "(" + " ".join(node) + ")"
    pad = "\t" * (indent + 1)
    parts = [dump(x, indent + 1) for x in node]
    head = []
    while parts and not isinstance(node[len(head)], list):
        head.append(parts.pop(0))
    return "(" + " ".join(head) + "".join("\n" + pad + p for p in parts) + ")"


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def unq(s):
    return s[1:-1].replace('\\"', '"').replace("\\\\", "\\") if s.startswith('"') else s


def find(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


# ---------------------------------------------------------------------- symbols

BT_SYMBOL = """
(symbol "FSC-BT1026D" (pin_names (offset 1.016)) (exclude_from_sim no) (in_bom yes) (on_board yes)
  (property "Reference" "U" (at 0 16.51 0) (effects (font (size 1.27 1.27))))
  (property "Value" "FSC-BT1026D" (at 0 -16.51 0) (effects (font (size 1.27 1.27))))
  (property "Footprint" "Bluespeaker:Feasycom_FSC-BT1026D" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (property "Datasheet" "https://www.feasycom.com/product/fsc-bt1026d/" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (property "Description" "Feasycom QCC3034 audio module. PLACEHOLDER pin numbers: set them from the datasheet." (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (symbol "FSC-BT1026D_0_1" (rectangle (start -10.16 13.97) (end 10.16 -13.97) (stroke (width 0.254) (type default)) (fill (type background))))
  (symbol "FSC-BT1026D_1_1"
    (pin power_in line (at -12.7 11.43 0) (length 2.54) (name "VBAT" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
    (pin power_in line (at -12.7 8.89 0) (length 2.54) (name "VDD_IO" (effects (font (size 1.27 1.27)))) (number "3" (effects (font (size 1.27 1.27)))))
    (pin input line (at -12.7 3.81 0) (length 2.54) (name "RST" (effects (font (size 1.27 1.27)))) (number "4" (effects (font (size 1.27 1.27)))))
    (pin input line (at -12.7 1.27 0) (length 2.54) (name "UART_RX" (effects (font (size 1.27 1.27)))) (number "6" (effects (font (size 1.27 1.27)))))
    (pin output line (at -12.7 -1.27 0) (length 2.54) (name "UART_TX" (effects (font (size 1.27 1.27)))) (number "5" (effects (font (size 1.27 1.27)))))
    (pin output line (at 12.7 6.35 180) (length 2.54) (name "I2S_BCLK" (effects (font (size 1.27 1.27)))) (number "7" (effects (font (size 1.27 1.27)))))
    (pin output line (at 12.7 3.81 180) (length 2.54) (name "I2S_WS" (effects (font (size 1.27 1.27)))) (number "8" (effects (font (size 1.27 1.27)))))
    (pin output line (at 12.7 1.27 180) (length 2.54) (name "I2S_DOUT" (effects (font (size 1.27 1.27)))) (number "9" (effects (font (size 1.27 1.27)))))
    (pin output line (at 12.7 -3.81 180) (length 2.54) (name "LED" (effects (font (size 1.27 1.27)))) (number "10" (effects (font (size 1.27 1.27)))))
    (pin power_in line (at 0 -16.51 90) (length 2.54) (name "GND" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
    (pin passive line (at 2.54 -16.51 90) (length 2.54) hide (name "GND" (effects (font (size 1.27 1.27)))) (number "11" (effects (font (size 1.27 1.27)))))
  )
)
"""


def load_symbol(lib_id):
    lib, name = lib_id.split(":")
    if lib == "Bluespeaker":
        sym = parse(BT_SYMBOL)[0]
    else:
        tree = parse((LIB / "symbols" / f"{lib}.kicad_symdir" / f"{name}.kicad_sym").read_text())[0]
        sym = [s for s in find(tree, "symbol") if unq(s[1]) == name][0]
    sym = [x for x in sym]
    sym[1] = q(lib_id)
    return sym


def symbol_pins(sym):
    """Return a list of dicts: number, name, x, y, angle, unit (unit 0 means all units)."""
    pins = []
    for sub in find(sym, "symbol"):
        m = re.match(r'"(.*)_(\d+)_(\d+)"', sub[1])
        unit = int(m.group(2))
        for p in find(sub, "pin"):
            at = find(p, "at")[0]
            name = unq(find(p, "name")[0][1])
            number = unq(find(p, "number")[0][1])
            hidden = "hide" in p or any(isinstance(x, list) and x[:2] == ["hide", "yes"] for x in p)
            pins.append(dict(number=number, name=name, x=float(at[1]), y=float(at[2]), angle=float(at[3]),
                             unit=unit, type=p[1], hidden=hidden))
    return pins


def symbol_units(sym):
    units = set()
    for sub in find(sym, "symbol"):
        m = re.match(r'"(.*)_(\d+)_(\d+)"', sub[1])
        if int(m.group(2)) > 0:
            units.add(int(m.group(2)))
    return sorted(units) or [1]


def symbol_extent(pins):
    if not pins:
        return 10, 10
    xs = [p["x"] for p in pins]
    ys = [p["y"] for p in pins]
    return max(xs) - min(xs) + 30, max(ys) - min(ys) + 12


def pin_net(part, pin):
    """Net for a symbol pin, by pin name first, then by number."""
    if pin["name"] in part.nets:
        return part.nets[pin["name"]]
    return part.nets.get(pin["number"])


# -------------------------------------------------------------------- schematic


def snap(v, g=1.27):
    return round(v / g) * g


def glabel(net, x, y, angle, just):
    """Global label, so that the net name has no sheet prefix and matches the PCB."""
    return ["global_label", q(net), ["shape", "passive"], ["at", f"{x:.2f}", f"{y:.2f}", str(angle)],
            ["fields_autoplaced", "yes"], ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", just]],
            ["uuid", q(uid())],
            ["property", q("Intersheetrefs"), q("${INTERSHEET_REFS}"), ["at", f"{x:.2f}", f"{y:.2f}", "0"],
             ["effects", ["font", ["size", "1.27", "1.27"]], ["hide", "yes"]]]]


def write_schematic(path, sheet_uuid):
    lib_symbols = {}
    for p in PARTS:
        if p.symbol not in lib_symbols:
            lib_symbols[p.symbol] = load_symbol(p.symbol)
    lib_symbols["power:PWR_FLAG"] = load_symbol("power:PWR_FLAG")

    out = []
    sym_uuids = {}
    errors = []

    # Lay the symbols out in columns, one column per group
    groups = []
    for p in PARTS:
        if p.group not in groups:
            groups.append(p.group)
    col_x = 25.4
    for g in groups:
        y = 30.48
        col_w = 0
        for p in [p for p in PARTS if p.group == g]:
            sym = lib_symbols[p.symbol]
            pins = symbol_pins(sym)
            w, h = symbol_extent(pins)
            col_w = max(col_w, w)
            ox, oy = snap(col_x + w / 2), snap(y + h / 2)
            y += h + 10
            u = uid()
            sym_uuids[p.ref] = u
            fields = [
                ["property", q("Reference"), q(p.ref), ["at", f"{ox:.2f}", f"{oy - h / 2 + 4:.2f}", "0"],
                 ["effects", ["font", ["size", "1.27", "1.27"]]]],
                ["property", q("Value"), q(p.value), ["at", f"{ox:.2f}", f"{oy + h / 2 - 4:.2f}", "0"],
                 ["effects", ["font", ["size", "1.27", "1.27"]]]],
                ["property", q("Footprint"), q(p.footprint), ["at", f"{ox:.2f}", f"{oy:.2f}", "0"],
                 ["effects", ["font", ["size", "1.27", "1.27"]], ["hide", "yes"]]],
                ["property", q("Datasheet"), q(""), ["at", f"{ox:.2f}", f"{oy:.2f}", "0"],
                 ["effects", ["font", ["size", "1.27", "1.27"]], ["hide", "yes"]]],
            ]
            for unit in symbol_units(sym):
                upins = [pn for pn in pins if pn["unit"] in (0, unit)]
                node = ["symbol", ["lib_id", q(p.symbol)], ["at", f"{ox:.2f}", f"{oy:.2f}", "0"], ["unit", str(unit)],
                        ["exclude_from_sim", "no"], ["in_bom", "no" if p.symbol.startswith("Mechanical:") else "yes"],
                        ["on_board", "yes"], ["dnp", "no"], ["uuid", q(u if unit == 1 else uid())], *fields]
                node += [["pin", q(pn["number"]), ["uuid", q(uid())]] for pn in upins]
                node.append(["instances", ["project", q(NAME), ["path", q("/" + sheet_uuid),
                                                                ["reference", q(p.ref)], ["unit", str(unit)]]]])
                out.append(node)
                # net labels and no-connect flags at each pin end
                for pn in upins:
                    x, y_ = ox + pn["x"], oy - pn["y"]
                    net = pin_net(p, pn)
                    if net is None:
                        if pn["name"] in p.nc or pn["number"] in p.nc or pn["hidden"]:
                            out.append(["no_connect", ["at", f"{x:.2f}", f"{y_:.2f}"], ["uuid", q(uid())]])
                        else:
                            errors.append(f"{p.ref} pin {pn['number']} ({pn['name']}) has no net")
                        continue
                    angle = {0: 180, 180: 0, 90: 270, 270: 90}[int(pn["angle"]) % 360]
                    just = "right" if angle in (180, 270) else "left"
                    out.append(glabel(net, x, y_, angle, just))
            # every net in the part must exist on a pin
            names = {pn["name"] for pn in pins} | {pn["number"] for pn in pins}
            for key in p.nets:
                if key not in names:
                    errors.append(f"{p.ref}: no pin '{key}' in {p.symbol}")
        col_x += col_w + 25

    # power flags
    y = 30.48
    for i, net in enumerate(POWER_FLAGS):
        x = snap(col_x + 10)
        yy = snap(y + i * 10)
        node = ["symbol", ["lib_id", q("power:PWR_FLAG")], ["at", f"{x:.2f}", f"{yy:.2f}", "0"], ["unit", "1"],
                ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"], ["uuid", q(uid())],
                ["property", q("Reference"), q(f"#FLG{i + 1:02d}"), ["at", f"{x:.2f}", f"{yy - 3:.2f}", "0"],
                 ["effects", ["font", ["size", "1.27", "1.27"]], ["hide", "yes"]]],
                ["property", q("Value"), q("PWR_FLAG"), ["at", f"{x:.2f}", f"{yy - 4:.2f}", "0"],
                 ["effects", ["font", ["size", "1.27", "1.27"]]]],
                ["property", q("Footprint"), q(""), ["at", f"{x:.2f}", f"{yy:.2f}", "0"],
                 ["effects", ["font", ["size", "1.27", "1.27"]], ["hide", "yes"]]],
                ["pin", q("1"), ["uuid", q(uid())]],
                ["instances", ["project", q(NAME), ["path", q("/" + sheet_uuid), ["reference", q(f"#FLG{i + 1:02d}")],
                                                    ["unit", "1"]]]]]
        out.append(node)
        out.append(glabel(net, x, yy, 0, "left"))

    title = ["title_block", ["title", q("Bluespeaker main PCB")], ["rev", q("A (placement)")],
             ["comment", "1", q("Generated by pcb/build.py from pcb/netlist.py. Edit netlist.py, then run build.py.")],
             ["comment", "2", q("U2 FSC-BT1026D pin numbers are placeholders. U3 uses the BQ25798 symbol (same RQM package).")]]
    doc = ["kicad_sch", ["version", "20250114"], ["generator", q("bluespeaker_build")], ["generator_version", q("9.0")],
           ["uuid", q(sheet_uuid)], ["paper", q("A0")], title,
           ["lib_symbols", *lib_symbols.values()], *out,
           ["sheet_instances", ["path", q("/"), ["page", q("1")]]], ["embedded_fonts", "no"]]
    path.write_text(dump(doc) + "\n")
    return sym_uuids, errors


# ------------------------------------------------------------------------- board


def mm(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


MODEL_SUBST = {
    # footprints whose library 3D model is missing: use a close match or a generated model
    "TSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.7mm_Mask3.1x4.05mm": "Package_SO.3dshapes/HTSSOP-28-1EP_4.4x9.7mm_P0.65mm_EP3.4x9.5mm.step",
    "Texas_RQM0029A_VQFN-29_4x4mm_P0.4mm": "generated/VQFN-29_4x4mm.step",
    "Feasycom_FSC-BT1026D": "generated/Feasycom_FSC-BT1026D.step",
}


def fix_models(fp, fp_name):
    """Point each 3D model at pcb/lib/3d.

    fp.Models() gives references into the list, so copy the values into new
    FP_3DMODEL objects, then clear the list and add the copies.
    """
    vec = lambda v: (v.x, v.y, v.z)  # noqa: E731
    saved = []
    for i in range(len(fp.Models())):
        m = fp.Models()[i]
        saved.append((str(m.m_Filename), vec(m.m_Offset), vec(m.m_Scale), vec(m.m_Rotation), m.m_Opacity, m.m_Show))
    fp.Models().clear()
    for filename, off, scale, rot, opacity, show in saved:
        base = Path(filename).name.replace(".wrl", ".step")
        stem = base[: -len(".step")]
        lib3d = Path(filename).parent.name  # e.g. Capacitor_SMD.3dshapes
        if stem in MODEL_SUBST:
            filename = "${KIPRJMOD}/lib/3d/" + MODEL_SUBST[stem]
        elif (LIB / "3d" / lib3d / base).exists():
            filename = "${KIPRJMOD}/lib/3d/" + f"{lib3d}/{base}"
        nm = pcbnew.FP_3DMODEL()
        nm.m_Filename = filename
        nm.m_Offset = pcbnew.VECTOR3D(*off)
        nm.m_Scale = pcbnew.VECTOR3D(*scale)
        nm.m_Rotation = pcbnew.VECTOR3D(*rot)
        nm.m_Opacity = opacity
        nm.m_Show = show
        fp.Add3DModel(nm)


def add_outline(board):
    x0, y0, w, h, r = BOARD["x0"], BOARD["y0"], BOARD["w"], BOARD["h"], BOARD["corner"]
    x1, y1 = x0 + w, y0 + h
    segs = [((x0 + r, y0), (x1 - r, y0)), ((x1, y0 + r), (x1, y1 - r)),
            ((x1 - r, y1), (x0 + r, y1)), ((x0, y1 - r), (x0, y0 + r))]
    for a, b in segs:
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(mm(*a))
        s.SetEnd(mm(*b))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(pcbnew.FromMM(0.1))
        board.Add(s)
    k = r * (1 - math.sqrt(0.5))
    arcs = [((x0, y0 + r), (x0 + k, y0 + k), (x0 + r, y0)), ((x1 - r, y0), (x1 - k, y0 + k), (x1, y0 + r)),
            ((x1, y1 - r), (x1 - k, y1 - k), (x1 - r, y1)), ((x0 + r, y1), (x0 + k, y1 - k), (x0, y1 - r))]
    for a, m_, b in arcs:
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
        s.SetArcGeometry(mm(*a), mm(*m_), mm(*b))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(pcbnew.FromMM(0.1))
        board.Add(s)


def add_text(board, text, x, y, layer, size=1.5):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(mm(x, y))
    t.SetLayer(layer)
    t.SetTextSize(mm(size, size))
    t.SetTextThickness(pcbnew.FromMM(size * 0.15))
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)


def write_board(path, sym_uuids):
    board = pcbnew.NewBoard(str(path))
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.m_MinThroughDrill = pcbnew.FromMM(0.2)  # thermal vias in the ESP32 and TAS5805M footprints (JLCPCB: 0.15 mm on 4 layers)
    ds.m_ViasMinSize = pcbnew.FromMM(0.4)
    add_outline(board)

    nets = {}

    def net(name):
        if name not in nets:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
            nets[name] = ni
        return nets[name]

    problems = []
    for p in PARTS:
        lib, name = p.footprint.split(":")
        fp = pcbnew.FootprintLoad(str(LIB / f"{lib}.pretty"), name)
        if fp is None:
            problems.append(f"{p.ref}: footprint {p.footprint} not found")
            continue
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(p.ref)
        fp.SetValue(p.value)
        fp.SetPath(pcbnew.KIID_PATH("/" + sym_uuids[p.ref]))
        fix_models(fp, name)
        board.Add(fp)
        fp.SetPosition(mm(*p.pos))
        fp.SetOrientationDegrees(p.rot)
        if p.side == "bottom":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)

        # nets: map symbol pins (by name) to pad numbers
        sym = load_symbol(p.symbol)
        pin_to_net = {}
        for pn in symbol_pins(sym):
            n = pin_net(p, pn)
            if n:
                pin_to_net[pn["number"]] = n
            elif pn["name"] in p.nc or pn["number"] in p.nc:
                # KiCad gives each no-connect pin its own net with this name
                pin_to_net[pn["number"]] = f"unconnected-({p.ref}-{pn['name']}-Pad{pn['number']})"
        for pad in fp.Pads():
            n = pin_to_net.get(pad.GetNumber())
            if n:
                pad.SetNet(net(n))

    add_text(board, "BLUESPEAKER MAIN  rev A", 212, 144.2, pcbnew.F_SilkS, 1.2)
    add_text(board, "FRONT (baffle side)", 212, 144.2, pcbnew.B_SilkS, 1.2)
    pcbnew.SaveBoard(str(path), board)
    return problems


# ----------------------------------------------------------------------- project


def write_project_files():
    libs = sorted(p.name[: -len(".pretty")] for p in LIB.glob("*.pretty"))
    fp_table = ["fp_lib_table", ["version", "7"]]
    for lib in libs:
        fp_table.append(["lib", ["name", q(lib)], ["type", q("KiCad")], ["uri", q(f"${{KIPRJMOD}}/lib/{lib}.pretty")],
                         ["options", q("")], ["descr", q("")]])
    (HERE / "fp-lib-table").write_text(dump(fp_table) + "\n")
    sym_table = ["sym_lib_table", ["version", "7"]]
    for d in sorted((LIB / "symbols").glob("*.kicad_symdir")):
        lib = d.name[: -len(".kicad_symdir")]
        sym_table.append(["lib", ["name", q(lib)], ["type", q("KiCad")], ["uri", q(f"${{KIPRJMOD}}/lib/symbols/{d.name}")],
                          ["options", q("")], ["descr", q("")]])
    (HERE / "sym-lib-table").write_text(dump(sym_table) + "\n")
    pro = HERE / f"{NAME}.kicad_pro"
    if not pro.exists():
        pro.write_text(json.dumps({"meta": {"filename": f"{NAME}.kicad_pro", "version": 1},
                                   "board": {"design_settings": {}}, "schematic": {}, "sheets": [], "text_variables": {}},
                                  indent=2))


def write_custom_symbols():
    d = LIB / "symbols" / "Bluespeaker.kicad_symdir"
    d.mkdir(parents=True, exist_ok=True)
    (d / "FSC-BT1026D.kicad_sym").write_text(
        '(kicad_symbol_lib (version 20241209) (generator "bluespeaker_build") (generator_version "9.0")' + BT_SYMBOL + ")\n")


def main():
    write_custom_symbols()
    write_project_files()
    sheet_uuid = uid()
    sym_uuids, errors = write_schematic(HERE / f"{NAME}.kicad_sch", sheet_uuid)
    problems = write_board(HERE / f"{NAME}.kicad_pcb", sym_uuids)
    for e in errors + problems:
        print("ERROR", e)
    print(f"{len(PARTS)} parts written")
    return 1 if errors or problems else 0


if __name__ == "__main__":
    sys.exit(main())
